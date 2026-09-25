"""The sanitiser's commit and reconcile steps, EXECUTED: the shipped blocks
lifted out of scripts/oxidized-to-config.sh and run under bash, with ssh
replaced by a local shell and real git repositories on both sides.

Measured 2026-09-25:
* labs/r6 was a repository whose commit failed for want of a user.email, and
  the script reported it as NOT VERSIONED with the `git init` recipe;
* a write whose commit failed was then STRANDED: the next run found nothing
  to copy, exited 0 before the commit step, and reported success (C15).

HOME is isolated so the operator's own git identity cannot make the
no-identity case pass.
"""

import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "oxidized-to-config.sh")
TEXT = open(SCRIPT, encoding="utf-8").read()


def _between(start: str, end: str) -> str:
    i = TEXT.index(start)
    return TEXT[i:TEXT.index(end, i) + len(end)]


def _function(name: str) -> str:
    i = TEXT.index(f"{name}() {{")
    return TEXT[i:TEXT.index("\n}\n", i) + 3]


GIT_ID = 'GIT_ID=(-c user.name=clab-sync -c user.email=clab-sync@nmas.invalid)'
COMMIT_BLOCK = _between("unversioned=()", 'do NOT run the git init recipe."\nfi')
RECONCILE = _between("declare -A REFUSED_DIRTY=()", "# <<< reconcile")


def _env(tmp_path):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"PATH": os.environ["PATH"], "HOME": str(home),
            "GIT_CONFIG_NOSYSTEM": "1"}


def _git(env, *args, check=True):
    return subprocess.run(["git", *args], env=env, check=check,
                          capture_output=True, text=True)


def _harness(tmp_path, devices: dict, body: str, oxidized: str = ""):
    """*devices* is {name: configs_dir}. The Oxidized repo, if given, is what
    GIT reads; every device's Oxidized node is its own name, kind router."""
    decl = "\n".join(f"DEVICES+=({n!r}); CFGDIR[{n}]={str(d)!r}; "
                     f"NODE[{n}]={n!r}; PLATFORM[{n}]=cisco_iosxe"
                     for n, d in devices.items())
    script = f"""
set -uo pipefail
ts=now; CLAB=clab
ssh() {{ bash -c "${{@: -1}}"; }}
declare -A NODE CFGDIR PLATFORM
DEVICES=()
{decl}
GIT=(git -C {oxidized!r})
{GIT_ID}
{_function("kind_for")}
{_function("sanitise")}
{_function("render_device")}
destinations() {{ for n in "${{DEVICES[@]}}"; do echo "${{CFGDIR[$n]}}"; done | sort -u; }}
{body}
"""
    return subprocess.run(["bash", "-c", script], capture_output=True,
                          text=True, env=_env(tmp_path), cwd=str(tmp_path))


def _lab(tmp_path, name, content="v1\n"):
    env = _env(tmp_path)
    lab = tmp_path / f"lab-{name}"
    (lab / "configs").mkdir(parents=True)
    _git(env, "init", "-q", str(lab))
    (lab / "configs" / f"{name}.cfg").write_text(content)
    _git(env, "-C", str(lab), "-c", "user.name=t", "-c", "user.email=t@t",
         "add", "-A")
    _git(env, "-C", str(lab), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-q", "-m", "initial")
    return lab / "configs"


def _oxidized(tmp_path, name, config):
    env = _env(tmp_path)
    ox = tmp_path / "oxidized"
    if not ox.exists():
        _git(env, "init", "-q", str(ox))
    (ox / name).write_text(config)
    _git(env, "-C", str(ox), "add", "-A")
    _git(env, "-C", str(ox), "-c", "user.name=o", "-c", "user.email=o@o",
         "commit", "-q", "-m", "poll")
    return ox, _git(env, "-C", str(ox), "rev-parse", "--short", "HEAD").stdout.strip()


RUNNING = "hostname r6\ninterface Loopback0\n ip address 10.255.1.16 255.255.255.255\n!\nend\n"


def _job_output(tmp_path, name, ox, sha):
    r = _harness(tmp_path, {}, f'raw="$(git -C {str(ox)!r} show {sha}:{name})"; '
                               f'render_device {name} router HEAD {sha} "$raw"')
    return r.stdout


# ---------------------------------------------------------------------------
# The commit step
# ---------------------------------------------------------------------------

def test_the_harness_reproduces_a_repo_with_no_identity(tmp_path):
    """Floor: without the fix this repo cannot commit here, or the test
    would pass for the wrong reason."""
    d = _lab(tmp_path, "r6")
    (d / "r6.cfg").write_text("v2\n")
    env = _env(tmp_path)
    _git(env, "-C", str(d.parent), "add", "-A")
    r = _git(env, "-C", str(d.parent), "commit", "-q", "-m", "x", check=False)
    said = (r.stderr + r.stdout).lower()
    assert r.returncode != 0, "the harness has an identity: the test is vacuous"
    assert "identity" in said or "email" in said, said


def test_a_repo_with_no_identity_commits_as_the_job(tmp_path):
    d = _lab(tmp_path, "r6")
    (d / "r6.cfg").write_text("v2\n")
    r = _harness(tmp_path, {"r6": d}, COMMIT_BLOCK)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"{d}: committed" in r.stdout
    author = _git(_env(tmp_path), "-C", str(d.parent), "log", "-1",
                  "--format=%an <%ae>").stdout.strip()
    assert author == "clab-sync <clab-sync@nmas.invalid>"


def test_a_failed_commit_is_named_with_gits_reason_and_is_not_unversioned(tmp_path):
    d = _lab(tmp_path, "r6")
    (d / "r6.cfg").write_text("v2\n")
    hook = d.parent / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'hook refused this commit' >&2\nexit 1\n")
    hook.chmod(0o755)
    r = _harness(tmp_path, {"r6": d}, COMMIT_BLOCK)
    assert "COMMIT FAILED in an existing repository - git said: hook refused" in r.stdout
    assert "NOT VERSIONED" not in r.stdout


def test_a_directory_that_is_not_a_repo_is_still_not_versioned(tmp_path):
    d = tmp_path / "bare" / "configs"
    d.mkdir(parents=True)
    (d / "r6.cfg").write_text("x\n")
    r = _harness(tmp_path, {"r6": d}, COMMIT_BLOCK)
    assert "NOT VERSIONED - the parent directory is not a git repo" in r.stdout


def test_unchanged_is_unchanged(tmp_path):
    d = _lab(tmp_path, "r6")
    r = _harness(tmp_path, {"r6": d}, COMMIT_BLOCK)
    assert f"{d}: unchanged" in r.stdout and r.returncode == 0, r.stdout


def test_the_commit_takes_only_the_jobs_own_files(tmp_path):
    """`git add -A configs` swept anything in the directory into a harvest."""
    d = _lab(tmp_path, "r6")
    (d / "r6.cfg").write_text("v2\n")
    (d / "notes.cfg").write_text("somebody's own file\n")
    r = _harness(tmp_path, {"r6": d}, COMMIT_BLOCK)
    assert f"{d}: committed" in r.stdout, r.stdout + r.stderr
    shown = _git(_env(tmp_path), "-C", str(d.parent), "show", "--name-only",
                 "--format=", "HEAD").stdout.split()
    assert shown == ["configs/r6.cfg"]


# ---------------------------------------------------------------------------
# Reconcile (C15)
# ---------------------------------------------------------------------------

def test_a_stranded_write_of_the_jobs_own_is_recorded_late(tmp_path):
    ox, sha = _oxidized(tmp_path, "r6", RUNNING)
    d = _lab(tmp_path, "r6")
    (d / "r6.cfg").write_text(_job_output(tmp_path, "r6", ox, sha))
    r = _harness(tmp_path, {"r6": d}, RECONCILE + "\nreconcile\n"
                 'echo "refused=${#REFUSED_DIRTY[@]}"', oxidized=str(ox))
    assert f"RECORDED LATE" in r.stdout and "refused=0" in r.stdout, r.stdout + r.stderr
    log = _git(_env(tmp_path), "-C", str(d.parent), "log", "-1",
               "--format=%s|%an").stdout.strip()
    assert log == f"harvest from oxidized {sha} (recorded late: an earlier run wrote it and its commit failed)|clab-sync"


def test_the_job_output_is_reproduced_for_the_version_in_the_header(tmp_path):
    """Oxidized moved on since the stranded write: the file still proves to
    be the job's own for the version its header names."""
    ox, old = _oxidized(tmp_path, "r6", RUNNING)
    stranded = _job_output(tmp_path, "r6", ox, old)
    # A change the SANITISER KEEPS. The first version added a `! comment`,
    # which sanitise() strips, so both versions rendered identically and a
    # reproduction from HEAD instead of the header's version passed this test.
    newer = RUNNING.replace(" ip address", " description added later\n ip address", 1)
    _, new = _oxidized(tmp_path, "r6", newer)
    assert _job_output(tmp_path, "r6", ox, new).splitlines()[3:] != \
        stranded.splitlines()[3:], "floor: the two versions must render differently"
    d = _lab(tmp_path, "r6")
    (d / "r6.cfg").write_text(stranded)
    r = _harness(tmp_path, {"r6": d}, RECONCILE + "\nreconcile\n"
                 'echo "refused=${#REFUSED_DIRTY[@]}"', oxidized=str(ox))
    assert "RECORDED LATE" in r.stdout and "refused=0" in r.stdout, r.stdout


def test_a_hand_edit_is_refused_neither_committed_nor_overwritten(tmp_path):
    ox, sha = _oxidized(tmp_path, "r6", RUNNING)
    d = _lab(tmp_path, "r6")
    edited = _job_output(tmp_path, "r6", ox, sha).replace(
        "interface Loopback0", "interface Loopback0\n description by hand")
    (d / "r6.cfg").write_text(edited)
    before = _git(_env(tmp_path), "-C", str(d.parent), "rev-parse", "HEAD").stdout
    r = _harness(tmp_path, {"r6": d}, RECONCILE + "\nreconcile\n"
                 'echo "refused=${!REFUSED_DIRTY[*]}: ${REFUSED_DIRTY[r6]:-}"',
                 oxidized=str(ox))
    assert "refused=r6:" in r.stdout, r.stdout + r.stderr
    assert f"the file says Oxidized {sha}; sanitising {sha} gives different content" in r.stdout
    assert (d / "r6.cfg").read_text() == edited, "not overwritten"
    assert _git(_env(tmp_path), "-C", str(d.parent), "rev-parse", "HEAD").stdout == before


def test_a_file_that_names_no_version_is_not_the_jobs(tmp_path):
    ox, _sha = _oxidized(tmp_path, "r6", RUNNING)
    d = _lab(tmp_path, "r6")
    (d / "r6.cfg").write_text("hostname r6\n! typed by hand\n")
    r = _harness(tmp_path, {"r6": d}, RECONCILE + "\nreconcile\n"
                 'echo "${REFUSED_DIRTY[r6]:-none}"', oxidized=str(ox))
    assert "does not name the Oxidized version" in r.stdout


def test_a_clean_destination_is_left_alone(tmp_path):
    ox, _sha = _oxidized(tmp_path, "r6", RUNNING)
    d = _lab(tmp_path, "r6")
    r = _harness(tmp_path, {"r6": d}, RECONCILE + "\nreconcile\n"
                 'echo "refused=${#REFUSED_DIRTY[@]}"', oxidized=str(ox))
    assert "refused=0" in r.stdout and "RECORDED LATE" not in r.stdout


def test_a_refusal_exits_nonzero_on_the_nothing_to_copy_path():
    """The whole point: the defect was an exit 0 hiding an unversioned
    change, and a refusal that exited 0 would reproduce it."""
    block = _between('  echo "Nothing to copy', "  exit 0")
    assert "[ ${#REFUSED_DIRTY[@]} -eq 0 ] || exit 3" in block
    tail = TEXT[TEXT.index('[ ${#failed[@]} -eq 0 ] || exit 3'):]
    assert "[ ${#REFUSED_DIRTY[@]} -eq 0 ] || exit 3" in tail


def test_reconcile_runs_before_the_early_exit_and_before_the_copy():
    assert TEXT.index("\nreconcile\n") < TEXT.index('echo "Nothing to copy')
    assert TEXT.index("\nreconcile\n") < TEXT.index("# Back up, copy, verify, commit")


class TestHelpersResolveBesideTheScriptNotThroughPath:
    """72 runs failed with `nmas-clab-targets: command not found` because the
    helper was on a login shell's PATH and not systemd's."""

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
