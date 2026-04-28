"""config_git.py

Git-based configuration versioning for device lists.

Each device list maintains a Git repository at:
  data/lists/{slug}/config_repo/

Device configurations are stored as {hostname}.cfg.

Workflow
--------
1. Configs are saved (Save All Configs / AI save).
2. Each config is written to the repo and staged (git add).
3. A comprehensive validation pipeline is created in Jenkins.
4. When that pipeline passes (and all previous function pipelines pass),
   the user can commit with a message.
5. The commit records the pipeline name so every git commit has exactly
   one corresponding Jenkins pipeline run.

A pipeline can only be linked to ONE commit.  Attempting to reuse a
pipeline that is already linked to a commit is prevented.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from typing import Optional

log = logging.getLogger(__name__)

_GIT_AUTHOR_NAME  = "NMAS"
_GIT_AUTHOR_EMAIL = "nmas@localhost"
_PC_FILE          = "pipeline_commits.json"   # per-list tracking file

# Lines stripped before storing — avoids noise in diffs
_VOLATILE_PREFIXES = (
    "! Last configuration", "! NVRAM config", "! No configuration",
    "Building configuration", "Current configuration", "ntp clock-period",
    "! Golden config", "! Saved:", "! Source:", "! Pre-change",
)


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


def write_and_stage(list_name: str, hostname: str, config_text: str) -> bool:
    """Write *config_text* for *hostname* and stage it (git add).  Returns True on success."""
    repo = _repo_dir(list_name)
    init_config_repo(list_name)

    fname = f"{_sanitise_hostname(hostname)}.cfg"
    path  = os.path.join(repo, fname)

    # Strip volatile lines so diffs focus on real config changes
    clean_lines = [
        ln for ln in config_text.splitlines()
        if not any(ln.startswith(p) for p in _VOLATILE_PREFIXES)
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(clean_lines) + "\n")

    rc, _, err = _git(repo, "add", fname)
    if rc != 0:
        log.warning("config_git: git add failed for %s/%s: %s", list_name, hostname, err)
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


def commit_configs(list_name: str, message: str, pipeline_name: str) -> Optional[str]:
    """
    Commit all staged changes and record the pipeline↔commit link.
    Returns the short commit hash on success, None on failure.
    """
    if not is_pipeline_available(list_name, pipeline_name):
        log.warning("config_git: pipeline '%s' already linked to a commit", pipeline_name)
        return None

    repo = _repo_dir(list_name)
    init_config_repo(list_name)

    rc, _, err = _git(repo, "commit", "-m", message)
    if rc != 0:
        log.error("config_git: commit failed: %s", err)
        return None

    rc2, hash_out, _ = _git(repo, "rev-parse", "--short", "HEAD")
    short_hash = hash_out.strip() if rc2 == 0 else "unknown"

    # Record the link
    pc = _load_pc(list_name)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    pc["pipelines"].setdefault(pipeline_name, {})["status"]       = "committed"
    pc["pipelines"][pipeline_name]["commit_hash"]  = short_hash
    pc["pipelines"][pipeline_name]["committed_at"] = now
    pc["pipelines"][pipeline_name]["message"]      = message
    pc["commits"][short_hash] = {
        "pipeline":     pipeline_name,
        "message":      message,
        "committed_at": now,
    }
    _save_pc(list_name, pc)
    log.info("config_git: committed %s (pipeline: %s)", short_hash, pipeline_name)
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


def _save_pc(list_name: str, data: dict) -> None:
    path = _pc_path(list_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp  = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def register_pending_pipeline(list_name: str, pipeline_name: str,
                               description: str = "") -> None:
    """Record a new pipeline as 'pending commit' after a config save batch."""
    pc = _load_pc(list_name)
    if pipeline_name not in pc["pipelines"]:
        pc["pipelines"][pipeline_name] = {
            "status":      "pending",
            "commit_hash": None,
            "created_at":  time.strftime("%Y-%m-%d %H:%M:%S"),
            "description": description,
        }
        _save_pc(list_name, pc)


def is_pipeline_available(list_name: str, pipeline_name: str) -> bool:
    """True if the pipeline has NOT already been linked to a commit."""
    pc    = _load_pc(list_name)
    used  = {v.get("pipeline") for v in pc["commits"].values()}
    entry = pc["pipelines"].get(pipeline_name, {})
    return pipeline_name not in used and entry.get("status") != "committed"


def get_available_pipelines(list_name: str) -> list[dict]:
    """
    Return pipelines registered for this list that have not been committed yet.
    Each entry is enriched with the pipeline's last Jenkins result.
    """
    pc   = _load_pc(list_name)
    used = {v.get("pipeline") for v in pc["commits"].values()}

    available = []
    for name, meta in pc["pipelines"].items():
        if name in used or meta.get("status") == "committed":
            continue
        available.append({
            "pipeline_name": name,
            "created_at":    meta.get("created_at", ""),
            "description":   meta.get("description", ""),
            "status":        meta.get("status", "pending"),
            "last_result":   None,
            "jenkins_ok":    False,
        })

    # Enrich with Jenkins last result
    try:
        from modules.jenkins_runner import load_results
        results = load_results() or {}
        pipes   = results.get("pipelines", {})
        for item in available:
            p = pipes.get(item["pipeline_name"], {})
            item["last_result"] = p.get("jenkins_result")
            item["last_build"]  = p.get("jenkins_build")
            item["jenkins_ok"]  = bool(p.get("jenkins_ok", False))
    except Exception:
        pass

    return sorted(available, key=lambda x: x["created_at"], reverse=True)


# ---------------------------------------------------------------------------
# Git log / status
# ---------------------------------------------------------------------------

def get_commit_log(list_name: str, limit: int = 40) -> list[dict]:
    """Return recent git commits enriched with pipeline status."""
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
            "pipeline":        meta.get("pipeline", ""),
            "pipeline_result": None,
            "pipeline_ok":     None,
        })

    # Enrich with Jenkins results
    try:
        from modules.jenkins_runner import load_results
        results = load_results() or {}
        pipes   = results.get("pipelines", {})
        for entry in entries:
            pname = entry.get("pipeline")
            if pname and pname in pipes:
                entry["pipeline_result"] = pipes[pname].get("jenkins_result")
                entry["pipeline_ok"]     = pipes[pname].get("jenkins_ok")
    except Exception:
        pass

    return entries


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


# ---------------------------------------------------------------------------
# Validation pipeline creation
# ---------------------------------------------------------------------------

def create_validation_pipeline(list_name: str, jenkins_cfg: dict,
                                description: str = "") -> Optional[str]:
    """
    Create a one-time comprehensive validation Jenkins pipeline for the
    current batch of staged config changes.  Returns the job name.
    """
    from modules.config     import list_slug
    from modules.jenkins_runner import create_jenkins_job

    slug      = list_slug(list_name)
    timestamp = int(time.time())
    job_name  = f"nmas-{slug}-validation-{timestamp}"

    import xml.sax.saxutils as _sax
    import textwrap

    groovy = textwrap.dedent(f"""\
        pipeline {{
            agent any
            options {{
                timeout(time: 20, unit: 'MINUTES')
                timestamps()
            }}
            stages {{
                stage('Install deps') {{
                    steps {{
                        bat 'pip install netmiko --quiet 2>NUL || echo netmiko already installed'
                    }}
                }}
                stage('Validate All Configs') {{
                    steps {{
                        bat 'python modules\\\\check_runner.py --validate-all --list-slug {_sax.escape(slug)}'
                    }}
                }}
            }}
            post {{
                success {{ echo 'Config validation PASSED - safe to commit.' }}
                failure {{ echo 'Config validation FAILED - fix issues before committing.' }}
                always  {{ echo "Result: ${{currentBuild.currentResult}}" }}
            }}
        }}
        """)

    xml_cfg = textwrap.dedent(f"""\
        <?xml version='1.1' encoding='UTF-8'?>
        <flow-definition plugin="workflow-job">
          <description>{_sax.escape(description or f"Config validation for {list_name}")}</description>
          <keepDependencies>false</keepDependencies>
          <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition"
                       plugin="workflow-cps">
            <script>{_sax.escape(groovy)}</script>
            <sandbox>true</sandbox>
          </definition>
          <triggers/>
          <disabled>false</disabled>
        </flow-definition>
        """)

    try:
        create_jenkins_job(jenkins_cfg, job_name, xml_cfg)
        register_pending_pipeline(list_name, job_name, description)
        log.info("config_git: created validation pipeline '%s'", job_name)
        return job_name
    except Exception as exc:
        log.error("config_git: failed to create validation pipeline: %s", exc)
        return None
