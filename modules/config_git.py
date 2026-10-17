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
the tab wrote only from D10.) Its reading (the log, a commit's diff, and the
status) left with today's Git tab at 7.8 (2026-10-17): History is their home.

Jenkins validation pipelines were removed in P.4 (docs/NSOT_CI.md). The
per-list `pipeline_commits.json` linked a commit to a pipeline before then;
since 2026-09-29 nothing reads it either, and the Git tab's "Pipeline (before
P.4)" column is gone (the operator: it meant nothing outside the project's
history and was populated only for commits older than P.4).
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_GIT_AUTHOR_NAME  = "NMAS"
_GIT_AUTHOR_EMAIL = "nmas@localhost"

# Lines stripped before storing — avoids noise in diffs
# Moved to modules/nsot/normalize.py. Re-exported here because this name is
# part of config_git's surface. The tuple is byte-identical to the one that
# lived here — see tests/test_normalize_equivalence.py.
from modules.nsot.normalize import REPO_PREFIXES as _VOLATILE_PREFIXES


# ---------------------------------------------------------------------------
# Low-level git wrapper
# ---------------------------------------------------------------------------

def _git(repo: str, *args) -> tuple[int, str, str]:
    """Run git in *repo*, pinned to it (`repo.run_git`, C931); return (rc, stdout, stderr)."""
    from modules.nsot.repo import run_git

    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"]     = _GIT_AUTHOR_NAME
    env["GIT_AUTHOR_EMAIL"]    = _GIT_AUTHOR_EMAIL
    env["GIT_COMMITTER_NAME"]  = _GIT_AUTHOR_NAME
    env["GIT_COMMITTER_EMAIL"] = _GIT_AUTHOR_EMAIL
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    try:
        r = run_git(repo, *args, env=env, timeout=30)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


# A list's repository is created by `modules.nsot.repo.init_repo`, the one
# `git init` (a network is born with it, C931). This module's own init, which
# nothing called, was removed (C944).


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


# Today's Git tab's readers (`get_commit_log`, `get_commit_diff`, `get_repo_status` with what
# each uncommitted path meant, and `publication`, which the Remote card's /remote/status read)
# left with the tab and the card at 7.8 (2026-10-17, P7-21). History reads the log and each
# commit through `modules/nsot/repo.py`, masked, and its header (`routes/v2._history_remote`)
# runs `git status` and asks `remote_publication.describe` for the remote's sentence.
