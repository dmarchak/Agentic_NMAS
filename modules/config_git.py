"""config_git.py

Git-based configuration versioning for device lists.

Each device list maintains a Git repository at:
  data/lists/{slug}/config_repo/

Device configurations are stored as {hostname}.cfg.

Workflow
--------
1. Configs are saved (Save All Configs / AI save).
2. Each config is written to the repo and staged (git add).
3. The user can commit with a message at any time.

Jenkins validation pipelines were removed in P.4 (docs/NSOT_CI.md). The
per-list `pipeline_commits.json` is still READ, so a commit linked to a
pipeline before then keeps showing that name in the log; nothing writes it.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from typing import Optional

log = logging.getLogger(__name__)

_GIT_AUTHOR_NAME  = "NMAS"
_GIT_AUTHOR_EMAIL = "nmas@localhost"
_PC_FILE          = "pipeline_commits.json"   # per-list tracking file

# Lines stripped before storing — avoids noise in diffs
# Moved to modules/nsot/normalize.py. Re-exported here because this name is
# part of config_git's surface. The tuple is byte-identical to the one that
# lived here — see tests/test_normalize_equivalence.py.
from modules.nsot.normalize import REPO_PREFIXES as _VOLATILE_PREFIXES


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _repo_dir(list_name: str) -> str:
    from modules.config import LISTS_DIR, list_slug
    return os.path.join(LISTS_DIR, list_slug(list_name), "config_repo")


def _pc_path(list_name: str) -> str:
    from modules.config import LISTS_DIR, list_slug
    return os.path.join(LISTS_DIR, list_slug(list_name), _PC_FILE)


# ---------------------------------------------------------------------------
# Low-level git wrapper
# ---------------------------------------------------------------------------

def _git(repo: str, *args) -> tuple[int, str, str]:
    """Run git in *repo*; return (rc, stdout, stderr)."""
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"]     = _GIT_AUTHOR_NAME
    env["GIT_AUTHOR_EMAIL"]    = _GIT_AUTHOR_EMAIL
    env["GIT_COMMITTER_NAME"]  = _GIT_AUTHOR_NAME
    env["GIT_COMMITTER_EMAIL"] = _GIT_AUTHOR_EMAIL
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    try:
        r = subprocess.run(
            ["git"] + list(args),
            cwd=repo, capture_output=True, text=True,
            env=env, timeout=30,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


# ---------------------------------------------------------------------------
# Repository initialisation
# ---------------------------------------------------------------------------

def init_config_repo(list_name: str) -> bool:
    """Initialise (or verify) the git repo for a device list.  Idempotent."""
    repo = _repo_dir(list_name)
    os.makedirs(repo, exist_ok=True)

    if os.path.isdir(os.path.join(repo, ".git")):
        return True

    # Try -b main first (git ≥ 2.28); fall back silently for older git
    rc, _, _ = _git(repo, "init", "-b", "main")
    if rc != 0:
        _git(repo, "init")

    # Seed so we always have a valid HEAD to diff against
    gi = os.path.join(repo, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w", encoding="utf-8") as fh:
            fh.write("*.swp\n*.tmp\n")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "--allow-empty", "-m",
         "Initialize device configuration repository")
    log.info("config_git: repo initialised for list '%s'", list_name)
    return True


# ---------------------------------------------------------------------------
# Stage / commit
# ---------------------------------------------------------------------------

def _sanitise_hostname(hostname: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in hostname)


def write_and_stage(list_name: str, hostname: str, config_text: str,
                    device_ip: str = "") -> bool:
    """Promote a golden config. Kept for compatibility; now commits immediately.

    This used to write a file and merely ``git add`` it, leaving the commit to
    whenever someone remembered to press Commit in the Git tab. The current
    golden and the latest commit could therefore disagree indefinitely, and
    history existed only by luck. It now routes through
    :func:`modules.nsot.repo.save_golden`, which commits in the same call.

    The manual stage/commit flow in the Git tab is unaffected — it is still how
    ``infra/`` and ad-hoc files are handled.
    """
    from modules.nsot.repo import GoldenItem, save_golden

    # allow_new=False, stated rather than defaulted: a manual golden save is
    # a save for a device that exists. Onboarding is the wizard and the Add
    # Device form, and nothing else should acquire the ability by a default
    # moving under it.
    result = save_golden(list_name,
                         [GoldenItem(hostname, config_text, device_ip)],
                         source="manual", actor="user", allow_new=False)
    if not result.get("ok"):
        log.warning("config_git: golden save failed for %s/%s: %s",
                    list_name, hostname, result.get("error"))
        return False
    return True


def has_staged_changes(list_name: str) -> bool:
    """True if there are staged-but-not-committed changes."""
    repo = _repo_dir(list_name)
    if not os.path.isdir(os.path.join(repo, ".git")):
        return False
    rc, _, _ = _git(repo, "diff", "--cached", "--quiet")
    return rc != 0     # exit 1 = differences exist


def get_staged_stat(list_name: str) -> str:
    """Human-readable summary of staged changes."""
    repo = _repo_dir(list_name)
    _, out, _ = _git(repo, "diff", "--cached", "--stat")
    return out


def commit_configs(list_name: str, message: str) -> Optional[str]:
    """Commit all staged changes. Returns the short hash, or None on failure."""
    repo = _repo_dir(list_name)
    init_config_repo(list_name)

    # WHO, and how that was established (D10): the Git tab's commits named
    # nobody. The route is gated `approve`, so the actor is the verified one.
    from modules.identity import request_actor
    from modules.nsot.repo import with_actor_verification
    message = with_actor_verification(
        f"{message.rstrip()}\n\nSource: manual\nActor: {request_actor()}\n")
    rc, _, err = _git(repo, "commit", "-m", message)
    if rc != 0:
        log.error("config_git: commit failed: %s", err)
        return None

    rc2, hash_out, _ = _git(repo, "rev-parse", "--short", "HEAD")
    short_hash = hash_out.strip() if rc2 == 0 else "unknown"

    log.info("config_git: committed %s", short_hash)
    return short_hash


# ---------------------------------------------------------------------------
# Pipeline-commit tracking
# ---------------------------------------------------------------------------

def _load_pc(list_name: str) -> dict:
    try:
        with open(_pc_path(list_name), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"pipelines": {}, "commits": {}}


# ---------------------------------------------------------------------------
# Git log / status
# ---------------------------------------------------------------------------

def get_commit_log(list_name: str, limit: int = 40) -> list[dict]:
    """Return recent git commits, with any pipeline linked before P.4."""
    repo = _repo_dir(list_name)
    if not os.path.isdir(os.path.join(repo, ".git")):
        return []

    fmt = "%H|%h|%s|%ai|%an"
    rc, out, _ = _git(repo, "log", f"--max-count={limit}", f"--format={fmt}")
    if rc != 0 or not out:
        return []

    pc        = _load_pc(list_name)
    meta_map  = pc.get("commits", {})

    entries = []
    for line in out.splitlines():
        parts = line.split("|", 4)
        if len(parts) < 5:
            continue
        full_hash, short_hash, subject, date, author = parts
        meta = meta_map.get(short_hash) or meta_map.get(full_hash[:7], {})
        entries.append({
            "hash":            full_hash,
            "short_hash":      short_hash,
            "message":         subject,
            "date":            date,
            "author":          author,
            # A pipeline linked before P.4 removed Jenkins: history, not state.
            "pipeline":        meta.get("pipeline", ""),
        })

    return entries


def get_commit_diff(list_name: str, commit_hash: str) -> Optional[dict]:
    """Return the changed-file list and full diff for one commit.

    Returns None if the repo doesn't exist or commit_hash isn't a plausible
    git hash (defends against argument injection into the git subprocess —
    e.g. a hash-shaped string starting with '-' being read as an option).
    """
    repo = _repo_dir(list_name)
    if not os.path.isdir(os.path.join(repo, ".git")):
        return None
    if not re.fullmatch(r"[0-9a-fA-F]{4,40}", commit_hash):
        return None

    rc, subject, _ = _git(repo, "show", "--no-patch", "--format=%s", commit_hash)
    if rc != 0:
        return None

    rc2, stat_out, _ = _git(repo, "show", "--stat", "--format=", commit_hash)
    rc3, diff_out, _ = _git(repo, "show", "--format=", commit_hash)

    return {
        "hash":    commit_hash,
        "message": subject,
        "stat":    stat_out if rc2 == 0 else "",
        "diff":    diff_out if rc3 == 0 else "",
    }


def get_repo_status(list_name: str) -> dict:
    """Return a summary dict: branch, staged changes, last commit."""
    repo = _repo_dir(list_name)
    if not os.path.isdir(os.path.join(repo, ".git")):
        return {"initialised": False}

    _, branch,      _ = _git(repo, "branch", "--show-current")
    _, staged_stat, _ = _git(repo, "diff", "--cached", "--stat")
    _, last_commit, _ = _git(repo, "log", "-1", "--format=%h %s (%ai)")

    return {
        "initialised":  True,
        "branch":       branch or "main",
        "has_staged":   bool(staged_stat.strip()),
        "staged_stat":  staged_stat,
        "last_commit":  last_commit,
    }
