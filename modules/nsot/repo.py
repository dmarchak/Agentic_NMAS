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
import re
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

#: `Source:` names the workflow and is free text by design (CLAUDE.md), so
#: any lowercase slug is recorded AS GIVEN. It used to be a list, and anything
#: outside it was silently rewritten to "manual": `golden_state` until
#: 2026-09-27, and every credential rotation (`rotation`) until the same day,
#: so all eleven rotation commits on the host name the wrong workflow. A
#: coercion is a record answering a different question from the one asked.
SOURCE_SLUG = re.compile(r"[a-z][a-z0-9_]*\Z")


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
                   ".nsot/staging/", ".nsot/migrated.json",
                   ".nsot/rolled_back.json", ".nsot/retry_log.json")


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


def with_actor_verification(message: str) -> str:
    """Add ``Actor-Verified:`` to a commit message that names an ``Actor:``.

    Every NSoT commit goes through :func:`git`, so the trailer is added HERE,
    once, rather than at each of the places a message is built: a writer that
    forgets it is the population-by-proxy failure all over again (D10, P.3
    step 10). A message that already says, or names no actor, is unchanged.
    """
    import re as _re
    m = _re.search(r"^Actor: (.+)$", message or "", _re.M)
    if not m or "\nActor-Verified:" in message:
        return message
    from modules.identity import actor_verification
    line = f"Actor-Verified: {actor_verification(m.group(1).strip())}"
    return message + (line + "\n" if message.endswith("\n") else "\n" + line)


def git(repo: str, *args) -> tuple:
    """Run a git command in *repo*. Returns ``(rc, stdout, stderr)``."""
    if "commit" in args and "-m" in args:
        i = args.index("-m")
        if i + 1 < len(args):
            args = args[:i + 1] + (with_actor_verification(args[i + 1]),) + args[i + 2:]
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


def git_raw(repo: str, *args) -> tuple:
    """:func:`git` without the ``.strip()``. For file CONTENT, not for display.

    ``git()`` trims stdout, which is right for a sha or a status line and wrong
    for a file read back out of history: it silently drops the trailing
    newline. Restore commits the ref's ``host_vars`` **verbatim**, so a stripped
    read would re-commit a one-byte change and label it "restore". Same shape
    as the porcelain-offset bug — a helper that tidies for display, used where
    exactness is the requirement.
    """
    _clear_stale_lock(repo)
    ensure_repo_hygiene(repo)
    try:
        proc = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True, text=True, timeout=GIT_TIMEOUT, env=_git_env(),
        )
        return proc.returncode, proc.stdout, proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", "git is not installed or not on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"git {args[0] if args else ''} timed out after {GIT_TIMEOUT}s"


# ---------------------------------------------------------------------------
# Staging: exactly the files a commit wrote (register C175)
# ---------------------------------------------------------------------------

#: The trees a commit may never stage whole. C104 made every READER take what
#: is committed; the WRITERS still ran `git add -A host_vars` (or `golden`,
#: `templates`, `.nsot`), so another device's uncommitted hand edit was
#: committed under an unrelated commit's subject, `Actor:` and `Source:`, and
#: the deploy then read it as committed intent and SENT it. The same defect
#: from the other end. Measured on the host 2026-09-28: 102 commits and none
#: carried a file for a device it did not name (latent), while four hand
#: commits of intent on 09-24 show the trigger, a hand edit, is practice.
#: The migration is the one declared exception (a one-shot first commit).
WHOLE_TREES = ("golden", "host_vars", "templates", ".nsot", "intended", "infra")

#: The manifest: the one tracked file under ``.nsot`` (measured on the host).
MANIFEST_REL = ".nsot/manifest.json"


class StagesMoreThanItWrote(ValueError):
    """A commit asked to stage a directory, or the index already holds a path
    outside the commit's scope that ``git commit`` would carry with it."""


def _rel(path: str) -> str:
    return path.replace(os.sep, "/").strip("/")


def stage_exactly(repo: str, paths: list) -> list:
    """Stage exactly *paths* (repo-relative FILES), and return them.

    Refuses a directory, and refuses when the index already holds a path
    outside *paths*: `git commit` takes the whole index, so a path somebody
    staged by hand would ride along just as an unstaged edit did under
    `add -A <dir>`. On a refusal nothing this call staged stays staged. A
    path that is on disk nowhere and not tracked has nothing to stage and is
    skipped (a file this commit deletes is still staged as a deletion)."""
    wanted = [_rel(p) for p in paths if p]
    for p in wanted:
        if p in WHOLE_TREES or os.path.isdir(os.path.join(repo, p)):
            raise StagesMoreThanItWrote(
                f"{p} is a directory: a commit stages the files it wrote, never a "
                f"tree, or another device's uncommitted edit rides along (C175)")
    _rc, before, _err = git(repo, "diff", "--cached", "--name-only")
    outside = sorted(set(l for l in (before or "").splitlines() if l.strip()) - set(wanted))
    if outside:
        raise StagesMoreThanItWrote(
            "the index already holds " + ", ".join(outside) + ", which this commit "
            "would carry under its own name; unstage it (git reset -- <path>) or "
            "commit it on its own. Nothing was committed")
    for p in wanted:
        if (not os.path.exists(os.path.join(repo, p))
                and git(repo, "ls-files", "--error-unmatch", "--", p)[0] != 0):
            continue    # nothing to stage, or its deletion is staged already (git rm)
        rc, _out, err = git(repo, "add", "-A", "--", p)
        if rc != 0:
            unstage(repo, wanted)
            raise StagesMoreThanItWrote(f"could not stage {p}: {err}")
    return wanted


def unstage(repo: str, paths: list) -> None:
    """Unstage exactly *paths*: never a blanket reset of a tree."""
    if paths:
        git(repo, "reset", "-q", "--", *[_rel(p) for p in paths])


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

    # A hygiene top-up wrote to .gitignore but nothing committed it, so the
    # tree stayed dirty forever and "no change left uncommitted" could never
    # be true again. Its own commit, so it is never mistaken for config.
    rc, dirty, _ = git(repo, "status", "--porcelain", "--", ".gitignore")
    if rc == 0 and dirty.strip():
        git(repo, "add", ".gitignore")
        rc, _, err = git(repo, "commit", "-m",
                         "repo: update .gitignore\n\nSource: hygiene\n")
        if rc == 0:
            log.info("repo: committed a .gitignore top-up in %s", repo)
        else:
            log.debug("repo: could not commit .gitignore: %s", err)
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
            manifest_before = _read_bytes(_manifest.manifest_path(repo))
            _manifest.clear_pending_rename(repo, identity, new_name, new_rel)
            own = [old_rel, new_rel, MANIFEST_REL]
            try:
                stage_exactly(repo, own)
                rc, _, err = git(repo, "commit", "-m", message)
            except StagesMoreThanItWrote as exc:
                rc, err = 1, str(exc)
            if rc != 0:
                # Put the move and the manifest back, so the rename stays
                # PENDING and is retried alone. Left staged, the next golden
                # save's `add golden .nsot` swept it into a content commit,
                # which is exactly what "a rename is committed alone" forbids.
                log.error("repo: rename commit failed, undone: %s", err)
                unstage(repo, own)
                try:
                    os.replace(os.path.join(repo, new_rel), old_abs)
                except OSError as exc:
                    log.error("repo: could not move %s back: %s", new_rel, exc)
                _write_bytes(_manifest.manifest_path(repo), manifest_before)
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


POST_DEPLOY_STAGING_REL = os.path.join(".nsot", "staging", "post_deploy")


def stage_post_deploy(repo: str, hostname: str, config_text: str) -> str:
    """Park a post-deploy capture where a crashed batch can recover it.

    Between stage 8.5 and the batch's single commit, a captured config exists
    on the device and in this process and nowhere else. A crash in that window
    loses the record of what was actually deployed — and the device cannot be
    re-read later to reconstruct it, because by then it may have changed again.

    Gitignored (``.nsot/staging/``): this is a crash file, not history. The
    history is the commit that follows.
    """
    directory = os.path.join(repo, POST_DEPLOY_STAGING_REL)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{_safe_name(hostname)}.cfg")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(config_text)
    return path


def staged_post_deploy(repo: str) -> dict:
    """``{hostname: config}`` for captures a batch has not yet committed."""
    directory = os.path.join(repo, POST_DEPLOY_STAGING_REL)
    if not os.path.isdir(directory):
        return {}
    out = {}
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".cfg"):
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as fh:
            out[name[:-4]] = fh.read()
    return out


def clear_post_deploy_staging(repo: str, hostnames: list = None) -> None:
    """Drop captures once they are committed."""
    directory = os.path.join(repo, POST_DEPLOY_STAGING_REL)
    if not os.path.isdir(directory):
        return
    for name in list(os.listdir(directory)):
        if not name.endswith(".cfg"):
            continue
        if hostnames is not None and name[:-4] not in {
                _safe_name(h) for h in hostnames}:
            continue
        try:
            os.remove(os.path.join(directory, name))
        except OSError:
            pass


def resolve_identity(repo: str, item):
    """The identity this device **already has**, or ``None``.

    This function cannot create an identity. That is the point, and it is a
    stronger guarantee than checking carefully inside one that can.

    The first version took an ``allow_new`` flag and minted when it was set.
    That put creation on a code path whose job is resolution, and the failure
    followed directly: an item arriving with a well-formed ``uid:`` that the
    manifest had never seen was *trusted outright*, because a supplied identity
    looked like a resolved one. ``devices.csv`` and the manifest turned out to
    hold different uid sets — migration minted into both independently — so six
    of nine devices carried a CSV uid naming nothing, and every deploy created
    a second manifest entry for a device that already had one.

    **A wrong identity is indistinguishable from a new device**, so a resolver
    that can create cannot tell them apart. Creation is
    :func:`adopt_identity`, named for what it does, called only by a caller
    that has decided this really is a new device.
    """
    if item.identity:
        # Supplied — but only if the manifest actually knows it. A uid that
        # names nothing is not evidence of anything.
        if _manifest.find_by_identity(repo, item.identity) is not None:
            return item.identity
        log.warning("repo: %s supplied identity %s, which the manifest does "
                    "not hold — resolving by address instead",
                    item.hostname, item.identity)

    identity, _entry = _manifest.find_by_ip(repo, item.mgmt_ip)
    if not identity:
        identity, _entry = _manifest.find_by_name(repo, item.hostname)
    return identity or None


def adopt_identity(repo: str, item) -> str:
    """Mint an identity for a device the manifest has never seen.

    The only place a device identity is created outside migration. Separate
    from :func:`resolve_identity` so that "I am looking this up" and "I am
    onboarding something new" cannot be the same call with a different
    argument.

    **That separation was a convention, not a rule, until the default moved.**
    ``save_golden``'s ``allow_new`` defaulted to ``True``, so four of its seven
    call sites could mint without anybody deciding they should: Save All, a
    pipeline path, ``config_git``, and a path reachable from the AI assistant.
    A device that appeared in the inventory got an identity as a side effect of
    the next routine capture, and the caller that was least entitled to create
    one — the assistant — was among those that could.

    The default is now ``False``. Exactly two callers pass ``True``: the
    onboarding wizard and the Add Device form, both of which exist to onboard.
    Everything else resolves or refuses.

        A rule enforced by a parameter whose default breaks it is a
        convention. The default is the behaviour.
    """
    identity = item.identity or _manifest.new_device_uid()
    log.info("repo: adopting %s (%s) as %s", item.hostname,
             item.mgmt_ip or "no ip", identity)
    return identity


#: Structural section kinds counted before a golden is overwritten. Each is a
#: top-level construct whose disappearance means the capture is not the same
#: device — not a config change, a different KIND of document.
SECTION_KINDS = {
    "interface": re.compile(r"^interface \S", re.M),
    "routing": re.compile(r"^router \S", re.M),
    "vrf": re.compile(r"^(?:vrf definition|ip vrf) \S", re.M),
    "line": re.compile(r"^line \S", re.M),
    "acl": re.compile(r"^ip access-list \S", re.M),
}


def section_counts(text: str) -> dict:
    """How many of each structural kind a config holds."""
    return {kind: len(rx.findall(text or "")) for kind, rx in SECTION_KINDS.items()}


def lost_sections(previous: str, incoming: str) -> dict:
    """Kinds the incoming config has FEWER of than the one it replaces.

    Returns ``{kind: (before, after)}``, empty when nothing was lost.
    """
    before, after = section_counts(previous), section_counts(incoming)
    return {kind: (before[kind], after[kind])
            for kind in SECTION_KINDS
            if after[kind] < before[kind]}


class GoldenWouldLoseSections(Exception):
    """A save that would drop structural sections from a device's record."""


def _guard_content(abs_path: str, hostname: str, incoming: str,
                   acknowledge: bool) -> None:
    """Refuse a save that silently shrinks a device's configuration.

    The chokepoint, not the caller. The credential rotation replaced r1's and
    r2's goldens with a two-line fragment — the output of
    ``show running-config | include ^username``, stored by mistake as a whole
    configuration — and every existing guard passed it, because all of them
    are about identity, emptiness, encoding and commit shape. None of them
    asked whether the content is plausibly the same device.

    Putting the check in ``save_golden`` means the next caller to make that
    mistake is refused without having to know the mistake exists. A guard that
    lives in one caller protects one caller.

    The comparison is against the PREVIOUS golden for this device, in the same
    spirit as the clab-sync truncation guard: counts of interfaces, routing
    processes, VRFs, lines and ACLs must not go DOWN. A genuine structural
    change — decommissioning interfaces, removing a routing process — is a
    real thing that must remain possible, so it is allowed with
    ``acknowledge_structural_change=True``. Explicit, recorded in the call,
    and impossible to reach by accident.
    """
    if acknowledge or not os.path.exists(abs_path):
        return
    with open(abs_path, encoding="utf-8") as fh:
        previous = fh.read()

    lost = lost_sections(previous, incoming)
    if not lost:
        return
    detail = ", ".join(f"{kind} {before}->{after}"
                       for kind, (before, after) in sorted(lost.items()))
    raise GoldenWouldLoseSections(
        f"{hostname}: the incoming config has fewer structural sections than "
        f"the golden it would replace ({detail}). This is what a filtered or "
        f"truncated capture looks like. If the device really did change "
        f"structurally, pass acknowledge_structural_change=True.")


def _baseline_wanted(baseline, source: str, changed_count: int) -> bool:
    """Does this save claim to mark the state of the whole network?"""
    if baseline is not None:
        return bool(baseline)
    return source in ("save_all", "migration") or changed_count > 1


def _baseline_decision(baseline, source: str, changed_count: int, measured: list,
                       inventory_size: int, skipped, intent: dict,
                       require_coverage: bool) -> tuple:
    """``(earned, reasons)``: ONE decision for both of save_golden's paths.

    A baseline asserts the network is at its committed intent (register C89
    (c), decided 2026-09-27), so beyond being wanted it needs coverage and
    every capture MATCHING COMMITTED INTENT. Against the golden it would be
    empty by construction, because the capture becomes the golden.

    Coverage is checked whenever the caller did not decide it (C91: a Save
    All that CHANGED a device took a baseline with another device skipped,
    because coverage was checked only on the no-change path). A caller that
    passes ``baseline=True`` has measured coverage itself (the deploy and
    restore paths' `_baseline_earned`)."""
    if not _baseline_wanted(baseline, source, changed_count):
        return False, []
    from modules.nsot.intent_match import baseline_denial

    reasons = []
    if require_coverage and not _covers_inventory(measured, inventory_size, skipped):
        named = ", ".join(sorted(s.get("hostname", "?") for s in (skipped or [])))
        reasons.append("not every inventory device was captured"
                       + (f" ({named} skipped)" if named else
                          f" ({len(measured)} of {inventory_size or 'an unstated number'})"))
    reasons += baseline_denial(intent)
    return not reasons, reasons


def _baseline_trailer(earned: bool, denied: list, baseline, source: str,
                      changed_count: int, caller_reasons) -> str:
    """The baseline DECISION as a trailer, or "" when none was made (7.2).

    The reasons a baseline was denied lived only in `save_golden()`'s return
    value, so a denial was drawn once on the result screen and could not be
    read again: Needs attention's "a baseline that was not earned, with its
    reason" had no durable source. It is decided BEFORE the commit now (every
    input is known by then) and recorded IN it, beside what it judged.
    ``baseline=False`` with no reasons means the save never claimed to mark
    the network (a single-device capture): no decision, no trailer.
    ``earned`` records the decision; the `baseline/<ts>` tag is the fact."""
    def one_line(text):
        return " ".join(str(text).split())

    if baseline is False and caller_reasons:
        return "Baseline: denied: " + "; ".join(one_line(r) for r in caller_reasons)
    if not _baseline_wanted(baseline, source, changed_count):
        return ""
    if earned:
        return "Baseline: earned"
    return "Baseline: denied: " + ("; ".join(one_line(r) for r in denied)
                                   or "no reason was recorded")


def _covers_inventory(measured: list, inventory_size: int, skipped) -> bool:
    """Was EVERY device in the inventory actually measured?

    A baseline taken with a device skipped would claim the network matches
    these goldens while saying nothing about one of its members. The caller
    supplies the inventory size and the skip list because only it knows them;
    absent that, coverage is unproven and the answer is no. Unproven is the
    right default — a baseline is a claim, and an unmade measurement cannot
    support one.
    """
    if inventory_size <= 0 or skipped:
        return False
    return len(measured) >= inventory_size


def save_golden(list_name: str, items: list, source: str = "manual",
                actor: str = "nmas", message: str = "", allow_new: bool = False,
                pipeline_id: str = None, baseline: bool = None,
                extra_trailers: list = None, extra_paths: list = None,
                acknowledge_structural_change: bool = False,
                inventory_size: int = 0, skipped: list = None,
                operational: dict = None, baseline_reasons: list = None) -> dict:
    """Promote golden configs for one or more devices in a single commit.

    *baseline_reasons*: a caller that decided the baseline itself (deploy and
    restore measure coverage, then pass ``baseline``) passes WHY it was not
    earned, so the commit can record it (`Baseline:` trailer, 7.2).

    Returns ``{"ok", "commit", "changed", "unchanged", "tags", "renamed", "error"}``.
    An unchanged device produces no commit but is still reported.
    """
    from modules.config import get_list_data_dir

    if not SOURCE_SLUG.match(source or ""):
        # Refused before anything is written. Recording it as "manual" would
        # be the coercion this replaced.
        return {"ok": False, "changed": [], "unchanged": [], "tags": [],
                "error": (f"source {source!r} is not a workflow name (lowercase "
                          f"letters, digits and underscores); nothing was saved")}
    repo = os.path.join(get_list_data_dir(list_name), "config_repo")

    rename_result = apply_pending_renames(repo, actor)

    changed, unchanged, pending = [], [], []
    with repo_lock(repo):
        init_repo(repo)
        os.makedirs(os.path.join(repo, "golden"), exist_ok=True)

        for item in items:
            identity = resolve_identity(repo, item)
            if identity is None:
                if not allow_new:
                    error = (
                        f"{item.hostname} ({item.mgmt_ip or 'no ip'}) is not in "
                        f"the manifest, so this save has nothing to attach it "
                        f"to. Onboard it first: the onboarding wizard is where "
                        f"an identity is created, and an existing device waits "
                        f"for adopt (7.10).")
                    log.error("repo: %s", error)
                    return {"ok": False, "error": error, "changed": [],
                            "unchanged": unchanged, "tags": [],
                            "renamed": rename_result["renamed"]}
                identity = adopt_identity(repo, item)
            rel = f"golden/{_safe_name(item.hostname)}.cfg"
            abs_path = os.path.join(repo, rel)
            content = golden_body(item.hostname, item.mgmt_ip, item.config_text)

            _manifest.upsert_device(repo, identity, item.hostname, item.mgmt_ip,
                                    netbox_id=item.netbox_id,
                                    platform=item.platform, golden=rel)

            if not _content_changed(abs_path, content):
                unchanged.append(item.hostname)
                continue

            pending.append((item, identity, rel, abs_path, content))

        # Validate EVERY pending write before performing ANY of them.
        #
        # Refusing mid-loop would leave the devices already written sitting on
        # disk, uncommitted, in the live repo — the same dirty-working-tree
        # failure the extra_paths handling below was fixed for. A Save All is
        # one commit over nine devices; a ninth device failing the guard must
        # not leave eight rewritten.
        try:
            for _item, _identity, _rel, abs_path, content in pending:
                _guard_content(abs_path, _item.hostname, content,
                               acknowledge_structural_change)
        except GoldenWouldLoseSections as exc:
            log.error("repo: %s", exc)
            return {"ok": False, "error": str(exc), "changed": [],
                    "unchanged": unchanged, "tags": [],
                    "renamed": rename_result["renamed"]}

        # Every capture in this save against its COMMITTED INTENT, computed
        # once, read by the trailer and the baseline decision alike (C89).
        from modules.nsot.intent_match import intent_match, trailer as _intent_trailer
        intent = {item.hostname: intent_match(repo, list_name, item.hostname,
                                               item.config_text, item.platform or "")
                  for item in items}

        # What each file held before this call, so a commit that fails can
        # put it back (None: the file is new). See _undo_golden_writes.
        before = {}
        for item, identity, rel, abs_path, content in pending:
            before[abs_path] = _read_bytes(abs_path)
            with open(abs_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
            changed.append({"hostname": item.hostname, "identity": identity,
                            "path": rel})

        # `extra_paths` is explicit so a template deploy's commit never starts
        # silently carrying intent. A restore passes "host_vars" because device
        # and intent are one unit for that event; nothing else does.
        own = [c["path"] for c in changed] + [MANIFEST_REL] + list(extra_paths or [])
        try:
            stage_exactly(repo, own)
        except StagesMoreThanItWrote as exc:
            log.error("repo: %s", exc)
            _undo_golden_writes(repo, before, [])
            return {"ok": False, "error": str(exc), "changed": [],
                    "unchanged": unchanged, "tags": []}

        # "No content changed" has to mean the whole commit, not just golden/.
        # A restore to a ref a device already matches changes no golden and
        # still moves that device's committed intent; returning early there
        # left the intent written but uncommitted — a dirty working tree in the
        # live repo, and a restore with no record.
        extra_dirty = []
        for rel in (extra_paths or []):
            _rc, out, _err = git(repo, "diff", "--cached", "--name-only", "--", rel)
            extra_dirty.extend(l for l in (out or "").splitlines() if l.strip())

        if not changed and not extra_dirty:
            # Scoped: unstage exactly what this function staged, never a
            # blanket reset of whatever else might be in the index.
            unstage(repo, own)

            # NO CHANGES IS A MEASUREMENT, AND IT IS THE BEST ONE.
            #
            # A baseline claims "the network matches the goldens at this
            # commit". Every device here was captured and compared against its
            # committed golden and found equal — which is precisely that
            # claim, established by observation rather than inferred from a
            # deploy having succeeded. Yet this branch returned before any
            # tagging, so a fleet that was perfectly in sync produced no
            # restore point, while one that had drifted did. The stronger the
            # evidence, the less the operator got.
            #
            # The tag goes on the EXISTING HEAD. Nothing is committed: an
            # empty commit to hang a tag on would be a false record of a
            # change, and the commit is not what the baseline is about.
            tags, baseline_tag = [], ""
            earned, denied = _baseline_decision(baseline, source, 0, unchanged,
                                                inventory_size, skipped, intent,
                                                require_coverage=True)
            if earned:
                _rc, head, _err = git(repo, "rev-parse", "HEAD")
                head = (head or "").strip()
                if _rc == 0 and head:
                    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                    baseline_tag = _unique_tag(repo, f"baseline/{stamp}", head)
                    if git(repo, "tag", "-a", baseline_tag, "-m",
                           _baseline_message(
                               f"network baseline — no changes; all "
                               f"{len(unchanged)} capture(s) verified equal to "
                               f"HEAD, via {source}", operational))[0] == 0:
                        tags.append(baseline_tag)
                        tags += _golden_state_tag(repo, stamp, head, operational)
                        log.info("repo: baseline %s at existing HEAD %s "
                                 "(%d device(s) verified equal)",
                                 baseline_tag, head[:12], len(unchanged))
                    else:
                        baseline_tag = ""

            # The hook fires here too, and for a reason that is easy to miss:
            # a baseline earned with nothing to commit is still a new PUBLIC
            # fact. Returning without it left the tag local forever -- the
            # restore point existed on this host and nowhere else, which is
            # the one property an off-host archive is for.
            #
            # Guarded on `tags`: a no-op save that earns no baseline has
            # produced nothing to publish, and waking the push path to do
            # nothing would make every unchanged Save All hit the network.
            if tags:
                from modules.nsot.hooks import run_post_commit
                _rc, head_sha, _e = git(repo, "rev-parse", "HEAD")
                run_post_commit({"list_name": list_name, "repo": repo,
                                 "sha": (head_sha or "").strip(),
                                 "source": source, "actor": actor,
                                 "tags": tags, "devices": []})
            return {"ok": True, "commit": "", "changed": [],
                    "unchanged": unchanged, "tags": tags,
                    "baseline": baseline_tag, "baseline_denied": denied,
                    "intent": intent,
                    "renamed": rename_result["renamed"],
                    "message": ("No content changed — no commit created."
                                + (f" Baseline {baseline_tag} tagged at the "
                                   "existing HEAD: every capture was verified "
                                   "equal to it." if baseline_tag else ""))}

        names = ", ".join(c["hostname"] for c in changed)
        subject = message or (
            # The subject names what HAPPENED. It said "golden: baseline N
            # device(s)" on every commit, tagged or not (C83): 15 of the host's
            # last 20 golden commits claimed a baseline none of them earned.
            # A baseline is the `baseline/<ts>` tag, decided after this commit
            # and able to be denied; the subject makes no claim about it.
            f"golden: {len(changed)} device(s) via {source}"
            + (f" {pipeline_id}" if pipeline_id else "")
        )
        trailers = [f"Source: {source}", f"Actor: {actor}"]
        if changed:
            trailers.append(f"Devices: {','.join(c['hostname'] for c in changed)}")
        elif extra_dirty:
            # No golden moved; the commit is here for what extra_paths carries.
            trailers.append(f"Paths: {','.join(sorted(extra_paths or []))}")
        for c in changed:
            trailers.append(f"Device-Id: {c['identity']}")
            trailers.append(f"Device-Name: {c['hostname']}")
        if pipeline_id:
            trailers.append(f"Pipeline-Id: {pipeline_id}")
        # COMPUTED, whatever the path (C89 (d)): which captures enshrined a
        # state that departs from committed intent, answerable from git.
        trailers.append(_intent_trailer(intent))
        # The baseline is DECIDED here, before the commit, and the decision
        # rides in it (7.2): every input is known now, and a denial's reasons
        # otherwise lived only in the return value.
        earned, denied = _baseline_decision(
            baseline, source, len(changed), [c["hostname"] for c in changed] + unchanged,
            inventory_size, skipped, intent, require_coverage=baseline is None)
        if baseline is False and baseline_reasons:
            denied = [str(r) for r in baseline_reasons]
        decision = _baseline_trailer(earned, denied, baseline, source, len(changed),
                                     baseline_reasons)
        if decision:
            trailers.append(decision)
        trailers.extend(extra_trailers or [])

        commit_message = f"{subject}\n\n" + "\n".join(trailers) + "\n"
        rc, _, err = git(repo, "commit", "-m", commit_message)
        if rc != 0:
            _undo_golden_writes(repo, before, own)
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
        # A baseline marks the state of the network at a moment. That is true
        # of a completed batch regardless of how many devices it changed, so a
        # caller that knows it is one says so rather than the count implying
        # it. Without this a single-device deploy left no reference to restore
        # the network to — the change was recorded and the moment was not.
        baseline_tag = ""
        if earned:
            baseline_tag = _unique_tag(repo, f"baseline/{stamp}", sha)
            if git(repo, "tag", "-a", baseline_tag, "-m",
                   _baseline_message(f"network baseline — {len(changed)} device(s) "
                                     f"via {source}", operational))[0] == 0:
                tags.append(baseline_tag)
                tags += _golden_state_tag(repo, stamp, sha, operational)
            else:
                baseline_tag = ""

        _prune_device_tags(repo, [c["hostname"] for c in changed])
        git(repo, "gc", "--auto")

    log.info("repo: saved golden for %d device(s) in '%s' — %s (%d unchanged)",
             len(changed), list_name, sha[:8], len(unchanged))

    from modules.nsot.hooks import run_post_commit
    run_post_commit({"list_name": list_name, "repo": repo, "sha": sha,
                     "source": source, "actor": actor, "tags": tags,
                     "devices": [c["hostname"] for c in changed]})

    # `baseline` on both return paths, so a caller never has to sift `tags`
    # to find out whether a restore point exists.
    return {"ok": True, "commit": sha, "changed": [c["hostname"] for c in changed],
            "unchanged": unchanged, "tags": tags, "baseline": baseline_tag,
            "baseline_denied": denied, "intent": intent,
            "renamed": rename_result["renamed"], "error": ""}


def _baseline_message(first_line: str, operational: dict = None) -> str:
    """A baseline tag's message: what it captured, and WHICH CLAIM it makes
    (register E7). Without a snapshot the claim is "configured", stated, so
    nobody reads a config-only baseline as a working network."""
    import json

    from modules.nsot.golden_state import claim_lines

    body = "\n".join(claim_lines(operational))
    message = f"{first_line}\n\n{body}"
    if operational:
        compact = {"taken_at": operational.get("taken_at"),
                   "claim": operational.get("claim"),
                   "outside_management": operational.get("outside_management"),
                   "devices": {h: {k: r.get(k) for k in ("working", "declared", "why",
                                                         "outside_management",
                                                         "interfaces_up", "routes")}
                               for h, r in (operational.get("devices") or {}).items()}}
        message += "\n\nOperational: " + json.dumps(compact, sort_keys=True)
    return message


def _golden_state_tag(repo: str, stamp: str, sha: str, operational: dict = None) -> list:
    """``golden-state/<stamp>`` at the same commit, ONLY when the snapshot says
    every device is working. A listing of these tags is the list of moments
    the network was known good; a baseline without one made the weaker claim."""
    if not operational or not operational.get("working"):
        return []
    from modules.nsot.golden_state import claim_lines

    tag = _unique_tag(repo, f"golden-state/{stamp}", sha)
    if git(repo, "tag", "-a", tag, "-m",
           "golden state — configured and working\n\n"
           + "\n".join(claim_lines(operational)))[0] == 0:
        return [tag]
    return []


def _read_bytes(path: str):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def _write_bytes(path: str, data) -> None:
    """Put *data* back at *path*; None means the file did not exist."""
    if data is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    with open(path, "wb") as fh:
        fh.write(data)


def _undo_golden_writes(repo: str, before: dict, staged=None) -> None:
    """A save whose commit FAILED leaves nothing behind (register C104).

    It used to return `changed: []` with every golden it had written still on
    disk AND staged. The drift checker, the NetBox import, onboarding and the
    agent read the golden from the working tree, so they treated content no
    save had committed as the approved golden; and the Git tab's manual
    commit (since removed) offered to commit it under any message, with no
    Intent-Match trailer. The index is unstaged for everything this call
    staged, each golden is put back as it was, and a new one is removed. The
    manifest is left as it is: it is updated eagerly by design, on the refusal
    paths too, and committed with the next save.
    """
    unstage(repo, staged or [])
    for path, data in before.items():
        _write_bytes(path, data)


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
        try:
            paths = stage_exactly(repo, paths)
        except StagesMoreThanItWrote as exc:
            log.error("repo: %s", exc)
            return {"ok": False, "error": str(exc)}

        rc, out, _ = git(repo, "status", "--porcelain")
        if not out.strip():
            return {"ok": True, "commit": "", "changed": [],
                    "message": "No changes to commit."}

        message = f"{subject}\n\n" + "\n".join(
            trailers + [f"Source: {source}"]) + "\n"
        rc, _, err = git(repo, "commit", "-m", message)
        if rc != 0:
            # Unstaged, never left for another commit to carry. The file stays
            # on disk: it is the person's edit, and the status bar names it.
            git(repo, "reset", "-q", "--", *paths)
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
    # *files* are relative to ``templates/``; only they are staged (C175).
    return _commit_paths(list_name, paths or [f"templates/{f}" for f in files],
                         subject, trailers, "template")


#: What an ``Actor:`` trailer may hold, and why the distinction is load-bearing.
#:
#: **An actor is who is accountable — not what ran.** The identity layer
#: already draws this line: it records a ``kind`` alongside the actor because
#: "a person approved this" and "a script approved this" are different facts
#: about a change, and it prefixes service tokens (``service:``) so no reader
#: mistakes a client id for a person.
#:
#: Three legitimate kinds:
#:
#: * a **person** — an email, or the OS user for a command run on the host;
#: * ``ai-agent`` — the autonomous agent, which is the exception that proves
#:   the rule: it genuinely decides and acts without anyone typing a command;
#: * ``service:<client-id>`` — a Cloudflare Access service token.
#:
#: A one-off script is **none of these**. Nobody is accountable to a program;
#: the person who ran it is. So a script records the person in ``Actor:`` and
#: names itself in ``Tool:``, which answers "what produced this commit"
#: without the history claiming a program decided something.
#:
#: The first repair commit (`host_vars: restore description text (ifname
#: expansion, 1.4)`) predates this and carries `Actor: description-repair`.
#: It is left as it is — rewriting published history to tidy a trailer costs
#: more than the inconsistency does — and is the reason the convention is
#: written down.
ACTOR_CONVENTION = ("person | ai-agent | service:<client-id>; a script names "
                    "the person in Actor and itself in Tool")


def save_host_vars(list_name: str, devices: list, actor: str = "user",
                   message: str = "", source: str = "extraction",
                   tool: str = "", extra_trailers: list = None,
                   paths: list = None) -> dict:
    """Commit ``host_vars`` after human review.

    Phase 3a writes extractions to a gitignored staging area precisely so that
    this — the first commit of a device's modelled configuration — has a person
    looking at a diff first.

    **``actor`` is who is accountable, never what ran.** See
    :data:`ACTOR_CONVENTION`. A one-off repair script passes the person who
    ran it and names itself in ``tool``; passing the script's own name as the
    actor makes the history claim a program decided something.

    ``source`` names the workflow (``extraction``, ``repair``, …) and is free
    text by design — the vocabulary grows with the tool, and an enum here
    would have to be edited before any new workflow could commit.
    """
    names = ", ".join(devices) if devices else "devices"
    subject = message or f"host_vars: commit extraction for {names}"
    trailers = [f"Actor: {actor}"]
    if tool:
        trailers.append(f"Tool: {tool}")
    trailers.append(f"Devices: {','.join(devices)}")
    trailers.extend(extra_trailers or [])
    # Exactly the named devices' files (C175): staging the whole tree
    # carried ANOTHER device's uncommitted edit under this commit's subject
    # and `Devices:` trailer, and the deploy then read it as committed intent.
    from modules.nsot.hostvars import committed_rel
    return _commit_paths(list_name, paths or [committed_rel(d) for d in devices],
                         subject, trailers, source)


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
        entry = {"sha": parts[0], "timestamp": parts[1],
                 "source": parts[2].strip(), "actor": parts[3].strip(),
                 "subject": parts[4]}
        # `source` stays what the RECORD says; a known misstatement rides
        # beside it (record_exceptions), never over it.
        from modules.nsot.record_exceptions import exception_for
        known = exception_for(parts[0])
        if known:
            entry["exception"] = dict(known)
        entries.append(entry)
    return entries


RESTORED_INTENT_STAGING_REL = os.path.join(".nsot", "staging", "restored_intent")


def stage_restored_intent(repo: str, hostname: str, yaml_text: str) -> str:
    """Park restored intent across the same crash window as a capture.

    Device and intent are one unit per device, and the intent is committed with
    the batch at the end. Between a device's restore succeeding and that commit
    there is a window where the device is at the ref and the intent is not —
    the fight-itself state, arrived at by failure rather than by design.
    """
    directory = os.path.join(repo, RESTORED_INTENT_STAGING_REL)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{_safe_name(hostname)}.yml")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(yaml_text)
    return path


def staged_restored_intent(repo: str) -> dict:
    """``{hostname: yaml}`` for intent a restore has not yet committed."""
    directory = os.path.join(repo, RESTORED_INTENT_STAGING_REL)
    if not os.path.isdir(directory):
        return {}
    out = {}
    for name in sorted(os.listdir(directory)):
        if name.endswith(".yml"):
            with open(os.path.join(directory, name), encoding="utf-8") as fh:
                out[name[:-4]] = fh.read()
    return out


def clear_restored_intent_staging(repo: str, hostnames: list = None) -> None:
    directory = os.path.join(repo, RESTORED_INTENT_STAGING_REL)
    if not os.path.isdir(directory):
        return
    keep = None if hostnames is None else {_safe_name(h) for h in hostnames}
    for name in list(os.listdir(directory)):
        if not name.endswith(".yml"):
            continue
        if keep is not None and name[:-4] not in keep:
            continue
        try:
            os.remove(os.path.join(directory, name))
        except OSError:
            pass


class ScopeRefused(PermissionError):
    """A read at a ref asked for a path the caller did not declare."""


class RefSource:
    """Read-only access to a declared subset of the repo at a ref.

    The scope rule for restore was a sentence in a docstring and a test that
    inspected one function's AST. That guards ``build_targets``; it does not
    guard the *capability*. A second restore path — item 2's intent restore is
    already scheduled — would read whatever it liked and inherit nothing.

    So the allowlist is a **constructor argument**. Widening it is a visible,
    deliberate act at the call site:

        RefSource(repo, ref)                          # golden/ only
        RefSource(repo, ref, allow=("golden/", "host_vars/"))

    Restore takes the first. It must never read ``templates/``,
    ``bindings.yml`` or ``.approvals.json``: templates are code, and rolling
    them back to restore a *network* would silently revert template fixes.
    Item 2 will take the second, and saying so at the call site is the point.

    Same move as ``resolve_identity`` losing the ability to mint and
    ``_command_keys`` refusing a raw line: turn "this function is careful" into
    "this capability is bounded".
    """

    def __init__(self, repo: str, ref: str, allow: tuple = ("golden/",)):
        self.repo = repo
        self.ref = ref
        self.allow = tuple(allow)

    def _check(self, rel_path: str) -> str:
        rel = (rel_path or "").lstrip("./")
        if ".." in rel.split("/"):
            raise ScopeRefused(f"{rel_path!r} escapes the repository")
        if not any(rel.startswith(prefix) for prefix in self.allow):
            raise ScopeRefused(
                f"{rel_path!r} is outside this source's declared scope "
                f"{self.allow}. Widen `allow` at the call site if the read is "
                "intended — restore must never read templates, bindings or "
                "approvals, because templates are code.")
        return rel

    def read(self, rel_path: str):
        """File content at the ref, or ``None`` if absent. Refuses out of scope."""
        rel = self._check(rel_path)
        # git_raw, not git: content is returned byte-for-byte. See git_raw().
        rc, out, _ = git_raw(self.repo, "show", f"{self.ref}:{rel}")
        return out if rc == 0 else None

    def listdir(self, rel_dir: str) -> list:
        """Names in a directory at the ref. Refuses out of scope."""
        rel = self._check(rel_dir.rstrip("/") + "/")
        rc, out, _ = git(self.repo, "ls-tree", "--name-only",
                         f"{self.ref}:{rel.rstrip('/')}")
        if rc != 0 or not out:
            return []
        return out.splitlines()

    # ── the two reads restore actually makes ───────────────────────────────

    def devices(self) -> list:
        """Device names with a golden config at this ref."""
        return [os.path.splitext(n)[0] for n in self.listdir("golden")
                if n.endswith(".cfg")]

    def golden(self, hostname: str):
        """One device's golden config at this ref."""
        return self.read(f"golden/{_safe_name(hostname)}.cfg")


def golden_commit_times(repo: str) -> dict:
    """``{relative path: ISO commit time}`` for everything under ``golden/``.

    **One subprocess for the whole store, not one per device.** The naive shape
    is `git log -1` per file, which on the reference fleet is nine processes
    every time a panel refreshes -- and enumeration is called from the drift
    checker, the event monitor, the AI tool layer and three routes.

    `--name-only` prints each commit's files after its own line, newest first,
    so the FIRST time a path appears is its most recent commit. Paths already
    seen are skipped rather than overwritten.
    """
    rc, out, _ = git(repo, "log", "--name-only", "--format=%x1e%cI", "--",
                     "golden")
    times = {}
    if rc != 0 or not out:
        return times
    for record in out.split("\x1e"):
        lines = [ln for ln in record.splitlines() if ln.strip()]
        if not lines:
            continue
        stamp, paths = lines[0], lines[1:]
        for rel in paths:
            times.setdefault(rel, stamp)
    return times


def list_goldens(list_name: str) -> list:
    """Every device that HAS a golden config, enumerated from the manifest.

    **This is the one enumerator.** Before it, enumeration and content came
    from different stores: `ai_assistant._list_golden_configs()` was
    `os.listdir(golden_configs/)` and nothing else, while
    `_load_golden_config_file()` resolved through the manifest. Every reader
    that asked "which devices have a golden?" -- the drift checker, the event
    monitor, `/templatize/report`, `check_runner`, `pipeline_builder`, the AI
    tool layer -- was answered by the deprecated store.

    The nine reference devices were therefore enumerable only because their
    pre-migration files still sat in `golden_configs/`. That coverage was
    inherited, not designed: a device onboarded AFTER the migration has a
    golden in the repo and no legacy file, so it was invisible to all of them
    -- checked by nothing, and reported by the event monitor as having no
    golden at all.

    Entries present only in the legacy store are still returned, flagged
    ``legacy``, so retiring the enumerator does not silently drop a device on
    the day it changes. :func:`legacy_only_goldens` is what reports them.

    ``saved_at`` comes from the COMMIT, not the file's mtime -- the same
    correction as the template preview, applied everywhere rather than at one
    call site.
    """
    from modules.config import get_list_data_dir
    from modules.nsot import manifest as _m

    list_dir = get_list_data_dir(list_name)
    repo = os.path.join(list_dir, "config_repo")

    times = golden_commit_times(repo)
    results, seen_names = [], set()
    # What HEAD holds, with sizes: a golden is a COMMITTED file (C104), so a
    # file on disk that no save committed is not enumerated as one.
    _rc, tree, _err = git(repo, "ls-tree", "-r", "-l", "HEAD", "--", "golden")
    committed = {}
    for line in (tree or "").splitlines():
        meta, _tab, name = line.partition("\t")
        parts = meta.split()
        if len(parts) >= 4 and parts[3].isdigit():
            committed[name] = int(parts[3])

    for identity, entry in sorted(_m.load(repo)["devices"].items(),
                                  key=lambda kv: (kv[1].get("name") or "").lower()):
        rel = entry.get("golden") or ""
        path = os.path.join(repo, rel)
        if not rel or rel.replace(os.sep, "/") not in committed:
            continue
        name = entry.get("name") or ""
        seen_names.add(name.lower())
        results.append({
            "identity":   identity,
            "hostname":   name,
            "device_ip":  entry.get("mgmt_ip", "") or name,
            "path":       path,
            "file":       os.path.basename(rel),
            "rel":        rel.replace(os.sep, "/"),
            "saved_at":   times.get(rel.replace(os.sep, "/"), ""),
            "size_bytes": committed[rel.replace(os.sep, "/")],
            "legacy":     False,
        })

    for entry in legacy_only_goldens(list_dir, seen_names):
        results.append(entry)

    return results


def legacy_only_goldens(list_dir: str, known_names: set = None) -> list:
    """Devices present in ``golden_configs/`` and NOT in the manifest.

    The deprecated store's **retirement condition**: when this returns
    nothing for every list, `_find_golden_config_file`'s header scan and the
    directory itself can go. "Deprecated" with no exit criterion never ends,
    so the number is reported on the Golden tab rather than left to be
    rediscovered.
    """
    import re as _re
    import time as _time

    known = {n.lower() for n in (known_names or set())}
    gdir = os.path.join(list_dir, "golden_configs")
    if not os.path.isdir(gdir):
        return []

    out = []
    for fname in sorted(os.listdir(gdir)):
        if not fname.endswith(".cfg"):
            continue
        path = os.path.join(gdir, fname)
        hostname = fname[:-4]
        device_ip = hostname
        try:
            with open(path, encoding="utf-8") as fh:
                first = fh.readline()
            # The legacy header carries an em dash. Do not "fix" it: it is what
            # the scan matches on.
            m = _re.search(r"—\s*(.+?)\s*\((\d[\d.]+)\)", first)
            if m:
                hostname = m.group(1).strip()
                device_ip = m.group(2).strip()
        except OSError:
            pass
        if hostname.lower() in known:
            continue
        stat = os.stat(path)
        out.append({
            "identity":   "",
            "hostname":   hostname,
            "device_ip":  device_ip,
            "path":       path,
            "file":       fname,
            # An mtime, and labelled as one: there is no commit behind a
            # legacy file, so this is the only timestamp that exists.
            "saved_at":   _time.strftime("%Y-%m-%d %H:%M",
                                         _time.localtime(stat.st_mtime)),
            "size_bytes": stat.st_size,
            "legacy":     True,
        })
    return out


#: Paths already warned about in this process, so a reader on a schedule (the
#: drift check, the agent's context) names a divergence once, not every pass.
_WORKTREE_WARNED: set = set()


def committed_golden(repo: str, rel: str) -> dict:
    """A golden AS COMMITTED, never as it sits on disk (C104's consumers).

    ``{"text", "commit", "source", "refused"}``. Every reader used to open the
    working-tree file, so a golden a failed or interrupted save had written,
    or one edited by hand on the host, was read as the approved golden by the
    drift check, the NetBox import, onboarding, the freshness gate and the
    agent. Now:

    * the text is ``HEAD:<rel>``, byte for byte (``git_raw``);
    * a working file that differs from it is IGNORED and named in the log,
      once per path per process, and the Git tab's status names it too;
    * a file on disk with no commit is refused, naming the path: a file
      nothing committed is not a golden;
    * the commit that last touched it must carry ``Source:``, the save path's
      trailer. Measured on the host 2026-09-27: all nine goldens' latest
      commits carry it (and ``Device-Id:``), so this refuses only a golden
      committed some other way, such as a hand ``git commit`` on the host.
    """
    rel = rel.replace(os.sep, "/")
    rc, text, _ = git_raw(repo, "show", f"HEAD:{rel}")
    if rc != 0:
        on_disk = os.path.exists(os.path.join(repo, rel))
        return {"text": None, "commit": "", "source": "",
                "refused": (f"{rel} is on disk and has never been committed; a "
                            f"file no save committed is not a golden. Capture "
                            f"the device to record it through the save path."
                            if on_disk else "")}
    rc, meta, _ = git(repo, "log", "-1",
                      "--format=%H%x1f%(trailers:key=Source,valueonly,separator=%x2C)",
                      "--", rel)
    sha, _sep, source = (meta or "").partition("\x1f")
    source = source.strip()
    _warn_if_worktree_differs(repo, rel, text)
    if not source:
        return {"text": None, "commit": sha, "source": "",
                "refused": (f"the last commit touching {rel} ({sha[:8]}) carries "
                            f"no Source: trailer, so it did not come through the "
                            f"save path. Capture the device to record it through "
                            f"that path.")}
    return {"text": text, "commit": sha, "source": source, "refused": ""}


def committed_golden_for(repo: str, entry) -> dict:
    """:func:`committed_golden` for a manifest entry: THE way a reader that
    holds an entry gets a golden. ``text`` is None with no ``refused`` when the
    entry names no committed golden. A refusal is logged by path, once per
    process, so a reader that only needs the text still leaves it visible.

    Every function that resolves a golden's path must read it through here,
    never `open()` it (tests/test_readers_use_what_is_committed.py). The first
    version of C104's fix changed one resolver and left six readers opening
    the file themselves, the deploy plan's capture among them."""
    from modules.nsot import manifest as _mf

    if not entry or not entry.get("golden"):
        return {"text": None, "commit": "", "source": "", "refused": "", "path": ""}
    rel = os.path.relpath(_mf.golden_path_for(repo, entry), repo).replace(os.sep, "/")
    record = committed_golden(repo, rel)
    record["path"] = rel
    if record["refused"] and ("refused", rel) not in _WORKTREE_WARNED:
        _WORKTREE_WARNED.add(("refused", rel))
        log.warning("repo: golden refused: %s", record["refused"])
    return record


def _warn_if_worktree_differs(repo: str, rel: str, committed_text: str) -> None:
    path = os.path.join(repo, rel)
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            on_disk = fh.read()
    except OSError:
        on_disk = None
    key = os.path.join(repo, rel)
    if on_disk != committed_text and key not in _WORKTREE_WARNED:
        _WORKTREE_WARNED.add(key)
        log.warning("repo: %s differs from its commit on disk; the committed "
                    "version is what every reader uses", rel)


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
    from modules.nsot.record_exceptions import WITHDRAWN_BASELINES, withdrawn_baseline

    baselines, present = [], set()
    for line in (out or "").splitlines() if rc == 0 else []:
        parts = line.split(sep)
        if len(parts) >= 3:
            commit = git(repo, "rev-parse", f"{parts[0]}^{{commit}}")[1].strip()
            present.add(commit)
            baselines.append({"tag": parts[0], "created": parts[1], "subject": parts[2],
                              "commit": commit, "withdrawn": withdrawn_baseline(commit),
                              "deleted": False,
                              **_baseline_claim(repo, parts[0]),
                              **_baseline_recorded(repo, commit)})
    # A withdrawn baseline whose tag is gone is drawn as that, where it was:
    # a row that vanished would read as a restore point that never existed.
    for sha, w in WITHDRAWN_BASELINES.items():
        if sha not in present and git(repo, "cat-file", "-e", f"{sha}^{{commit}}")[0] == 0:
            created = git(repo, "log", "-1", "--format=%aI", sha)[1].strip()
            baselines.append({"tag": w["tag"], "created": created, "subject": "",
                              "commit": sha, "withdrawn": w, "deleted": True})
    # Newest first; the tag's own UTC name breaks a tie between tags made in
    # the same second.
    return sorted(baselines, key=lambda b: (b["created"], b["tag"]), reverse=True)


def _baseline_recorded(repo: str, commit: str) -> dict:
    """What the baseline's own commit says it EARNED (7.2's `Baseline:` and
    C89's `Intent-Match:` trailers). A baseline taken before those were
    recorded says nothing, and is drawn as "not recorded", never as fine: its
    tag was taken on coverage alone, and the newest such tag on the host holds
    a device broken by hand (C70)."""
    _rc, body, _ = git(repo, "log", "-1", "--format=%B", commit)
    decision = intent = ""
    for line in (body or "").splitlines():
        if line.startswith("Baseline: "):
            decision = line[len("Baseline: "):].strip()
        elif line.startswith("Intent-Match: "):
            intent = line[len("Intent-Match: "):].strip()
    if not decision:
        return {"decision": "unrecorded", "intent_match": intent,
                "decision_detail": ("taken before baselines recorded what they earned: "
                                    "nothing says every device was at its committed intent"
                                    + (f" (Intent-Match: {intent})" if intent else ""))}
    return {"decision": "earned" if decision == "earned" else "denied",
            "intent_match": intent, "decision_detail": decision}


def withdrawn_ref(repo: str, ref: str):
    """The withdrawal recorded for the commit *ref* names, or None. The
    restore routes refuse a withdrawn baseline, whichever screen asked."""
    from modules.nsot.record_exceptions import withdrawn_baseline

    rc, sha, _ = git(repo, "rev-parse", f"{ref}^{{commit}}")
    return withdrawn_baseline(sha.strip()) if rc == 0 else None


def device_restore_points(repo: str, hostname: str) -> list:
    """Where ONE device can be restored from, newest first (C80, 7.1 step 5).

    Its golden now (``HEAD``), its own golden tags, and every baseline that
    holds a golden for it. A baseline predating the device is not a restore
    point for it: re-applying it would leave the device exactly as it is, so
    offering it would be a choice that does nothing. Each point says which
    kind it is and, for a baseline, which claim the baseline makes."""
    sep = "@@|@@"
    name = _safe_name(hostname)
    points = [{"ref": "HEAD", "kind": "head", "created": "",
               "subject": "its golden now"}]
    rc, out, _ = git(repo, "tag", "--list", f"golden/{name}/*",
                     f"--format=%(refname:short){sep}%(creatordate:iso-strict){sep}%(subject)")
    own = []
    for line in (out.splitlines() if rc == 0 else []):
        parts = line.split(sep)
        if len(parts) >= 3:
            own.append({"ref": parts[0], "kind": "device", "created": parts[1],
                        "subject": parts[2]})
    for b in list_baselines(repo):
        if b["deleted"] or b["withdrawn"]:
            continue    # a withdrawn restore point is not offered (C70)
        if name in devices_at(repo, b["tag"]):
            own.append({"ref": b["tag"], "kind": "baseline", "created": b["created"],
                        "subject": b["subject"], "claim": b["claim"],
                        "claim_detail": b["claim_detail"]})
    return points + sorted(own, key=lambda p: p["created"], reverse=True)


def _baseline_claim(repo: str, tag: str) -> dict:
    """WHICH CLAIM a baseline makes (register E7), from its own message.

    A baseline written before E7 carries no `Claim:` line and can only have
    captured configuration, so it reads "configured": the weaker claim, drawn
    as that, never implying the stronger. ``claim_detail`` says why."""
    from modules.nsot.golden_state import CONFIGURED, WORKING

    _rc, body, _ = git(repo, "tag", "-l", "--format=%(contents)", tag)
    for line in (body or "").splitlines():
        if line.startswith("Claim: "):
            text = line[len("Claim: "):]
            working = text.startswith(WORKING)
            return {"claim": WORKING if working else CONFIGURED, "claim_detail": text}
    return {"claim": CONFIGURED,
            "claim_detail": "taken before baselines recorded an operational "
                            "snapshot: configuration only"}


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
