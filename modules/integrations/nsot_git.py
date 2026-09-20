"""NSoT git repo integration (Phase 0: remote reachability test only).

Uses ``subprocess`` git, matching :mod:`modules.config_git` — no GitPython.
The repo itself is still owned by ``config_git``; Phase 2 redesigns that module
in place.
"""

import logging
import subprocess

from modules.integrations.base import IntegrationClient
from modules.settings_schema import get_setting

log = logging.getLogger(__name__)


class NsotGitIntegration(IntegrationClient):
    name = "nsot_git"
    label = "NSoT git repo"
    url_key = "nsot_git_remote_url"
    secret_keys = ("nsot_git_token",)
    plain_keys = ("nsot_git_repo_path", "nsot_git_branch", "nsot_git_author_name",
                  "nsot_git_author_email", "nsot_git_auto_push", "nsot_git_auth_mode")

    def is_configured(self) -> bool:
        # A local repo is a complete VCS; a remote is optional.
        return bool(get_setting("nsot_git_repo_path", "") or self.url)

    def test_connection(self) -> dict:
        """``git ls-remote`` against the configured remote.

        With no remote set this reports local-only rather than an error: the
        plan treats the remote as optional.
        """
        remote = self.url
        if not remote:
            return {"ok": True, "message": "Local repo only (no remote configured)"}
        try:
            # Secrets are never passed on the command line; credentials come
            # from the host's SSH key or git credential helper.
            proc = subprocess.run(
                ["git", "ls-remote", "--heads", remote],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode != 0:
                return {"ok": False, "error": (proc.stderr or "git ls-remote failed").strip()[:300]}
            refs = [ln for ln in proc.stdout.splitlines() if ln.strip()]
            return {"ok": True, "message": f"{len(refs)} branch(es) on remote"}
        except FileNotFoundError:
            return {"ok": False, "error": "git is not installed or not on PATH"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "git ls-remote timed out after 15s"}
        except Exception as exc:              # noqa: BLE001
            return {"ok": False, "error": str(exc)}
