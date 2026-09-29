"""config_git.py

Git-based configuration versioning for device lists.

Each device list maintains a Git repository at:
  data/lists/{slug}/config_repo/

Device configurations are stored as {hostname}.cfg.

Every write to this repository commits in the same call, through
``modules.nsot.repo`` (goldens through ``save_golden()``). The Git tab's
manual commit was REMOVED (2026-09-27): it committed whatever the index held,
and the only thing that could be in the index was what a FAILED operation
left staged, so a golden nobody had saved successfully could be committed
under any message, without its Intent-Match trailer. Measured on the
deployment host: used three times (30 Aug, 1 Sep, 15 Sep), before saves
committed in their own call, and since then it had nothing to commit but
residue. (First recorded as "never used": the search looked for a trailer
the tab wrote only from D10.) What this module keeps is
reading: the log, a commit's diff, and the status, which names anything left
uncommitted and what to do about it.

Jenkins validation pipelines were removed in P.4 (docs/NSOT_CI.md). The
per-list `pipeline_commits.json` linked a commit to a pipeline before then;
since 2026-09-29 nothing reads it either, and the Git tab's "Pipeline (before
P.4)" column is gone (the operator: it meant nothing outside the project's
history and was populated only for commits older than P.4).

The status also says whether the repository is PUBLISHED (C223): the
`remote-publication` reader's comparison of HEAD with the remote's own
branch, in the one sentence `remote_publication.describe()` makes.
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
    from modules.nsot.repo import commit as _commit
    _commit(repo, "Initialize device configuration repository", list_name=list_name,
            allow_empty=True, source="init")
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


# ---------------------------------------------------------------------------
# Git log / status
# ---------------------------------------------------------------------------

def get_commit_log(list_name: str, limit: int = 40) -> list[dict]:
    """Return recent git commits."""
    repo = _repo_dir(list_name)
    if not os.path.isdir(os.path.join(repo, ".git")):
        return []

    fmt = "%H|%h|%s|%ai|%an"
    rc, out, _ = _git(repo, "log", f"--max-count={limit}", f"--format={fmt}")
    if rc != 0 or not out:
        return []

    entries = []
    for line in out.splitlines():
        parts = line.split("|", 4)
        if len(parts) < 5:
            continue
        full_hash, short_hash, subject, date, author = parts
        entries.append({
            "hash":            full_hash,
            "short_hash":      short_hash,
            "message":         subject,
            "date":            date,
            "author":          author,
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


#: What an uncommitted path means, by where it is. Every writer in the
#: program commits in the same call, so anything here outside `.nsot/` was
#: left by an operation that failed or was interrupted, or edited on the host.
_UNCOMMITTED_MEANS = {
    "golden": ("a golden that no save committed. Readers of the working tree "
               "(drift, the NetBox import, the agent) treat it as the approved "
               "golden. Capture the device to record what it holds now through "
               "the save path, or discard it on the host (git checkout)."),
    "host_vars": ("intent that was not committed. Deploy reads committed intent "
                  "only; open the intent editor for this device to commit it."),
    "templates": ("a template that was not committed. Its approval is already "
                  "refused while it differs; save it again in the template "
                  "editor."),
    ".nsot": ("identity changes recorded by an inventory refresh or a save; "
              "committed with the next golden save, by design."),
}
_UNCOMMITTED_ELSE = ("nothing in NMAS writes here, so it was changed on the "
                     "host. Commit or discard it there.")


def get_repo_status(list_name: str) -> dict:
    """The branch, the last commit, and EVERY uncommitted path with what it
    means. It used to report only STAGED changes and call everything else
    "working tree clean": a golden rewritten and left uncommitted is
    unstaged, so the one state this bar exists to show read as clean."""
    repo = _repo_dir(list_name)
    if not os.path.isdir(os.path.join(repo, ".git")):
        return {"initialised": False}

    _, branch,      _ = _git(repo, "branch", "--show-current")
    _, last_commit, _ = _git(repo, "log", "-1", "--format=%h %s (%ai)")
    rc, porcelain, err = _git(repo, "status", "--porcelain=v1",
                              "--untracked-files=all")
    if rc != 0:
        return {"initialised": True, "ok": False, "branch": branch or "main",
                "last_commit": last_commit, "publication": publication(list_name),
                "error": f"could not read the repository's status: {err}"}
    uncommitted = []
    for line in porcelain.splitlines():
        # Parsed, never sliced: `_git` strips its output, so the first line's
        # leading space (" M golden/r1.cfg") is gone and a fixed column
        # slice ate the path's first letter (found by the exact-path test).
        m = re.match(r"^\s*(\S{1,2})\s+(.*)$", line)
        if not m:
            continue
        path = m.group(2).split(" -> ")[-1].strip('"')
        top = path.split("/", 1)[0]
        uncommitted.append({"path": path, "state": m.group(1),
                            "means": _UNCOMMITTED_MEANS.get(top, _UNCOMMITTED_ELSE)})
    return {
        "initialised":  True,
        "ok":           True,
        "branch":       branch or "main",
        "last_commit":  last_commit,
        "uncommitted":  uncommitted,
        "publication":  publication(list_name),
    }


def publication(list_name: str) -> dict:
    """Is this list's history on its remote: the reader's stored comparison
    of HEAD with the remote's own branch, as the one sentence (C223)."""
    from modules.readers import remote_publication as P

    try:
        return P.describe(P.status_for(list_name))
    except Exception as exc:                   # noqa: BLE001
        return {"level": "warning", "state": "not_read", "detail": "",
                "clause": f"whether it is pushed could not be read: {exc}"}
