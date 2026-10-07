"""The NSoT git repositories: one per device list, DERIVED, never configured.

**What this probe used to ask, and why it was wrong** (the operator,
2026-09-28, C171). Phase 0 described ONE global repository, located by
settings (`nsot_git_repo_path`, `nsot_git_remote_url`, `nsot_git_branch`,
`nsot_git_auto_push`, `nsot_git_auth_mode`, `nsot_git_token`). Phase 2
replaced it: each list's repository is `data/lists/<slug>/config_repo`
(`modules/nsot/repo.py`), and each list's remote is its own `remote.json`
(`modules/nsot/remote.py`; `archive.py` refuses the global URL on purpose,
because one URL cannot express one repository per network). Nothing reads
those six settings any more except this probe, which reported "not
configured" for repositories committing all evening: a working integration
reported unconfigured, C166's lesson (a healthy rule reading no data) in the
status bar.

**So the probe asks about what the program uses.** For every registered
list: is the derived repository a readable repository with a HEAD, and what
does its own remote record say (none, the last push, a failed push)? It is
always CONFIGURED, by derivation; a list with no repository yet (it has
never committed) is stated, never a fault. The dead settings are C171's
7.7 work; only `nsot_git_author_name` and `nsot_git_author_email` are read
(the commit identity, `repo.py`).
"""

import logging
import os
import subprocess

from modules.integrations.base import IntegrationClient

log = logging.getLogger(__name__)


class NsotGitIntegration(IntegrationClient):
    name = "nsot_git"
    label = "NSoT git repo"
    url_key = "nsot_git_remote_url"
    secret_keys = ("nsot_git_token",)
    plain_keys = ("nsot_git_repo_path", "nsot_git_branch", "nsot_git_author_name",
                  "nsot_git_author_email", "nsot_git_auto_push", "nsot_git_auth_mode")

    def is_configured(self) -> bool:
        """Always: every list's repository is derived from its data directory."""
        return True

    def test_connection(self) -> dict:
        from modules.config import LISTS_DIR
        from modules.device import get_device_lists
        from modules.nsot import remote as R

        try:
            lists = get_device_lists()
        except Exception as exc:                        # noqa: BLE001
            return {"ok": False, "error": f"the list registry could not be read: {exc}"}
        if not lists:
            return {"ok": True, "message": "configured by derivation; no device list exists yet"}
        parts, bad = [], []
        for entry in lists:
            name = entry["name"]
            repo = os.path.join(LISTS_DIR, entry.get("filename") or "", "config_repo")
            if not os.path.isdir(repo):
                parts.append(f"{name}: no repository yet (nothing committed)")
                continue
            try:
                out = subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"],
                                     capture_output=True, text=True, timeout=10, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                bad.append(f"{name}: git could not read {repo} ({type(exc).__name__})")
                continue
            if out.returncode != 0:
                bad.append(f"{name}: {repo} is not a readable repository "
                           f"({(out.stderr or 'no HEAD').strip()[:120]})")
                continue
            head = out.stdout.strip()
            remote, unreadable = R.config_or_refusal(name)
            if unreadable:
                bad.append(f"{name}: HEAD {head}; {unreadable}")
                continue
            if not remote:
                parts.append(f"{name}: HEAD {head}, no remote")
                continue
            failure, last = remote.get("last_push_failure"), remote.get("last_push") or {}
            if failure:
                bad.append(f"{name}: HEAD {head}; its last push FAILED at {failure.get('at')}: "
                           f"{failure.get('reason', '')[:160]}")
                continue
            parts.append(f"{name}: HEAD {head}, remote {remote.get('owner')}/{remote.get('repo')}, "
                         f"last push {last.get('at') or 'never recorded'}")
        if bad:
            return {"ok": False, "error": "configured by derivation; " + "; ".join(bad + parts)}
        return {"ok": True, "message": "configured by derivation; " + "; ".join(parts)}
