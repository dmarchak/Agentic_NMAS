"""The sanitiser's commit step, EXECUTED: the block lifted out of the shipped
script and run under bash, with ssh replaced by a local shell.

Measured 2026-09-25: labs/r6 was a repository whose commit failed for want of
a user.email, and the script reported it as NOT VERSIONED with the `git init`
recipe. HOME is isolated here so the operator's own git identity cannot make
the no-identity case pass.
"""

import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "oxidized-to-config.sh")


def _block() -> str:
    text = open(SCRIPT, encoding="utf-8").read()
    start = text.index("GIT_ID=(")
    end = text.index("do NOT run the git init recipe.\"\nfi", start) + len(
        "do NOT run the git init recipe.\"\nfi")
    tail = text.index('[ ${#failed[@]} -eq 0 ] || exit 3')
    return text[start:end] + "\n" + text[tail:tail + len('[ ${#failed[@]} -eq 0 ] || exit 3')]


def _run(tmp_path, dirs):
    harness = f"""
set -uo pipefail
ts=now; CLAB=clab
ssh() {{ bash -c "${{@: -1}}"; }}
destinations() {{ printf '%s\\n' {' '.join(repr(str(d)) for d in dirs)}; }}
{_block()}
"""
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "home"),
           "GIT_CONFIG_NOSYSTEM": "1"}
    os.makedirs(env["HOME"], exist_ok=True)
    return subprocess.run(["bash", "-c", harness], capture_output=True,
                          text=True, env=env, cwd=str(tmp_path))


def _repo(tmp_path, name, hook=None):
    lab = tmp_path / name
    (lab / "configs").mkdir(parents=True)
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "home"),
           "GIT_CONFIG_NOSYSTEM": "1"}
    os.makedirs(env["HOME"], exist_ok=True)
    subprocess.run(["git", "init", "-q", str(lab)], check=True, env=env)
    (lab / "configs" / "x.cfg").write_text("v1\n")
    subprocess.run(["git", "-C", str(lab), "-c", "user.name=t", "-c",
                    "user.email=t@t", "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(lab), "-c", "user.name=t", "-c",
                    "user.email=t@t", "commit", "-q", "-m", "initial"],
                   check=True, env=env)
    (lab / "configs" / "x.cfg").write_text("v2\n")
    if hook:
        h = lab / ".git" / "hooks" / "pre-commit"
        h.write_text(f"#!/bin/sh\necho '{hook}' >&2\nexit 1\n")
        h.chmod(0o755)
    return lab / "configs"


def test_the_harness_reproduces_a_repo_with_no_identity(tmp_path):
    """Floor: without the fix, this repo cannot commit here -- or the test
    would pass for the wrong reason."""
    d = _repo(tmp_path, "r6")
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "home"),
           "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "-C", str(d.parent), "add", "-A"], env=env)
    r = subprocess.run(["git", "-C", str(d.parent), "commit", "-q", "-m", "x"],
                       env=env, capture_output=True, text=True)
    said = (r.stderr + r.stdout).lower()
    assert r.returncode != 0, "the harness has an identity: the test is vacuous"
    assert "identity" in said or "email" in said, said


def test_a_repo_with_no_identity_commits_as_the_job(tmp_path):
    d = _repo(tmp_path, "r6")
    r = _run(tmp_path, [d])
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"{d}: committed" in r.stdout
    author = subprocess.run(["git", "-C", str(d.parent), "log", "-1",
                             "--format=%an <%ae>"], capture_output=True,
                            text=True).stdout.strip()
    assert author == "clab-sync <clab-sync@nmas.invalid>"


def test_a_failed_commit_is_named_with_gits_reason_and_is_not_unversioned(
        tmp_path):
    d = _repo(tmp_path, "r6", hook="hook refused this commit")
    r = _run(tmp_path, [d])
    assert r.returncode == 3
    assert "COMMIT FAILED in an existing repository - git said: hook refused" in r.stdout
    assert "NOT VERSIONED" not in r.stdout
    assert "git init" not in r.stdout.replace("do NOT run the git init recipe", "")


def test_a_directory_that_is_not_a_repo_is_still_not_versioned(tmp_path):
    d = tmp_path / "bare" / "configs"
    d.mkdir(parents=True)
    r = _run(tmp_path, [d])
    assert r.returncode == 0
    assert "NOT VERSIONED - the parent directory is not a git repo" in r.stdout


def test_unchanged_is_unchanged(tmp_path):
    d = _repo(tmp_path, "lab")
    (d / "x.cfg").write_text("v1\n")
    r = _run(tmp_path, [d])
    assert "unchanged" in r.stdout and r.returncode == 0


class TestHelpersResolveBesideTheScriptNotThroughPath:
    """72 runs failed with `nmas-clab-targets: command not found` because the
    helper was on a login shell's PATH and not systemd's. The PATH below is
    systemd-like: no ~/bin."""

    ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}

    def test_a_copy_without_helpers_refuses_by_name(self, tmp_path):
        import shutil
        copy = tmp_path / "oxidized-to-config.sh"
        shutil.copy(SCRIPT, copy)
        r = subprocess.run(["bash", str(copy), "--yes"], capture_output=True,
                           text=True, env=self.ENV, cwd=str(tmp_path))
        assert r.returncode == 2
        assert f"helper not found or not executable: {tmp_path}/nmas-clab-targets" in r.stdout

    def test_a_symlink_to_the_repo_copy_finds_its_helpers(self, tmp_path):
        link = tmp_path / "oxidized-to-config.sh"
        link.symlink_to(SCRIPT)
        r = subprocess.run(["bash", str(link), "--yes"], capture_output=True,
                           text=True, env={**self.ENV, "REPO": str(tmp_path / "none")},
                           cwd=str(tmp_path), timeout=60)
        assert "helper not found" not in r.stdout, r.stdout
        assert "command not found" not in r.stdout + r.stderr
