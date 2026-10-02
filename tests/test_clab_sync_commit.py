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
BASE_TAG = "baseline/20261001T235242Z"
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
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    decl = "\n".join(f"DEVICES+=({n!r}); CFGDIR[{n}]={str(d)!r}; "
                     f"NODE[{n}]={n!r}; PLATFORM[{n}]=cisco_iosxe"
                     for n, d in devices.items())
    script = f"""
set -uo pipefail
ts=now; CLAB=clab; SRC_SHA=abc1234; REF=HEAD; BASE_TAG={BASE_TAG}; OUT={str(out)!r}
ssh() {{ bash -c "${{@: -1}}"; }}
declare -A NODE CFGDIR PLATFORM
DEVICES=()
{decl}
GIT=(git -C {oxidized!r})
{GIT_ID}
{_function("kind_for")}
{_function("sanitise")}
{_function("render_device")}
{_function("config_body")}
destinations() {{ for n in "${{DEVICES[@]}}"; do echo "${{CFGDIR[$n]}}"; done | sort -u; }}
mapfile -t COPIED_DIRS < <(destinations)
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
                               f'render_device {name} router "$raw"')
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
    assert log == (f"harvest from oxidized {sha} (recorded late: an earlier run wrote it and "
                   "its commit failed): r6|clab-sync")


def _moved_on(tmp_path):
    """Oxidized moved on since the stranded write. A change the SANITISER
    KEEPS: the first version added a `! comment`, which sanitise() strips, so
    both versions rendered identically and a reproduction from HEAD instead of
    the file's own version passed."""
    ox, old = _oxidized(tmp_path, "r6", RUNNING)
    newer = RUNNING.replace(" ip address", " description added later\n ip address", 1)
    _, new = _oxidized(tmp_path, "r6", newer)
    assert _job_output(tmp_path, "r6", ox, new) != _job_output(tmp_path, "r6", ox, old), \
        "floor: the two versions must render differently"
    return ox, old, new


def test_a_stranded_write_from_an_older_oxidized_version_is_found_by_the_search(tmp_path):
    """C313: a file names no version, so the device's recent versions are tried."""
    ox, old, _new = _moved_on(tmp_path)
    d = _lab(tmp_path, "r6")
    (d / "r6.cfg").write_text(_job_output(tmp_path, "r6", ox, old))
    r = _harness(tmp_path, {"r6": d}, RECONCILE + "\nreconcile\n"
                 'echo "refused=${#REFUSED_DIRTY[@]}"', oxidized=str(ox))
    assert f"own output for Oxidized {old}" in r.stdout and "refused=0" in r.stdout, r.stdout


def test_a_pre_c313_file_is_reproduced_for_the_version_its_header_names(tmp_path):
    ox, old, _new = _moved_on(tmp_path)
    d = _lab(tmp_path, "r6")
    (d / "r6.cfg").write_text(f"!\n! r6 - from Oxidized HEAD {old}\n!\n"
                              + _job_output(tmp_path, "r6", ox, old))
    r = _harness(tmp_path, {"r6": d}, RECONCILE + "\nreconcile\n"
                 'echo "refused=${#REFUSED_DIRTY[@]}"', oxidized=str(ox))
    assert f"own output for Oxidized {old}" in r.stdout and "refused=0" in r.stdout, r.stdout


def test_a_stranded_write_of_this_runs_own_baseline_build_is_recorded_late(tmp_path):
    """Plan item 4: the file the run would write from the baseline is the job's own."""
    ox, _sha = _oxidized(tmp_path, "r6", RUNNING)
    d = _lab(tmp_path, "r6")
    built = _job_output(tmp_path, "r6", ox, _sha).replace("ip address", "description b\n ip address")
    (tmp_path / "out").mkdir(exist_ok=True)
    (tmp_path / "out" / "r6.cfg").write_text(built)
    (d / "r6.cfg").write_text(built)
    r = _harness(tmp_path, {"r6": d}, RECONCILE + "\nreconcile\n"
                 'echo "refused=${#REFUSED_DIRTY[@]}"', oxidized=str(ox))
    assert f"own output for {BASE_TAG}" in r.stdout and "refused=0" in r.stdout, r.stdout + r.stderr
    log = _git(_env(tmp_path), "-C", str(d.parent), "log", "-1", "--format=%s").stdout.strip()
    assert log == (f"startup from {BASE_TAG} (recorded late: an earlier run wrote it and its "
                   "commit failed): r6")


def test_a_hand_edit_is_refused_neither_committed_nor_overwritten(tmp_path):
    ox, sha = _oxidized(tmp_path, "r6", RUNNING)
    d = _lab(tmp_path, "r6")
    edited = f"!\n! r6 - from Oxidized HEAD {sha}\n!\n" + _job_output(tmp_path, "r6", ox, sha).replace(
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


def test_a_hand_edit_with_no_header_matches_no_version_and_is_refused(tmp_path):
    ox, _old, _new = _moved_on(tmp_path)
    d = _lab(tmp_path, "r6")
    (d / "r6.cfg").write_text("hostname r6\n! typed by hand\n")
    r = _harness(tmp_path, {"r6": d}, RECONCILE + "\nreconcile\n"
                 'echo "${REFUSED_DIRTY[r6]:-none}"', oxidized=str(ox))
    assert ("sanitising each of the last 20 Oxidized versions of r6 gives different content"
            in r.stdout), r.stdout + r.stderr
    assert (d / "r6.cfg").read_text() == "hostname r6\n! typed by hand\n"


def test_a_clean_destination_is_left_alone(tmp_path):
    ox, _sha = _oxidized(tmp_path, "r6", RUNNING)
    d = _lab(tmp_path, "r6")
    r = _harness(tmp_path, {"r6": d}, RECONCILE + "\nreconcile\n"
                 'echo "refused=${#REFUSED_DIRTY[@]}"', oxidized=str(ox))
    assert "refused=0" in r.stdout and "RECORDED LATE" not in r.stdout


def test_a_refusal_exits_nonzero_on_the_nothing_to_copy_path():
    """The whole point: the defect was an exit 0 hiding an unversioned
    change, and a refusal that exited 0 would reproduce it."""
    block = _between('if [ $((changed + newfiles)) -eq 0 ]; then', "  exit 0")
    assert "[ ${#REFUSED_DIRTY[@]} -eq 0 ] || exit 3" in block
    tail = TEXT[TEXT.index('[ ${#failed[@]} -eq 0 ] || exit 3'):]
    assert "[ ${#REFUSED_DIRTY[@]} -eq 0 ] || exit 3" in tail


def test_reconcile_runs_before_the_early_exit_and_before_the_copy():
    assert TEXT.index("\nreconcile\n") < TEXT.index('if [ $((changed + newfiles)) -eq 0 ]; then')
    assert TEXT.index("\nreconcile\n") < TEXT.index("# Back up, copy, verify, commit")


#: Port 9 (discard) on loopback: nothing listens, so a connection is refused
#: at once. Never the script's default, which is the live NMAS.
CLOSED_PORT_URL = "http://127.0.0.1:9"


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
        """The helper must be FOUND and RUN, and must reach no NMAS.

        `NMAS_URL` is a closed local port. Left at the script's default it
        asked the LIVE NMAS for its map: from the laptop that address is
        firewalled and the test waited 15 s for a timeout; on the host it IS
        the NMAS, and the live app logged each run's GET (2026-09-26). What
        stopped it going further was only this test's `REPO`, which names
        nothing. A refused connection is also immediate, and it proves the
        helper ran, where "no error text" alone does not."""
        link = tmp_path / "oxidized-to-config.sh"
        link.symlink_to(SCRIPT)
        env = {**self.ENV, "REPO": str(tmp_path / "none"), "NMAS_URL": CLOSED_PORT_URL}
        r = subprocess.run(["bash", str(link), "--yes"], capture_output=True,
                           text=True, env=env, cwd=str(tmp_path), timeout=60)
        assert "helper not found" not in r.stdout, r.stdout
        assert "command not found" not in r.stdout + r.stderr
        assert "the NMAS could not be asked" in r.stdout, r.stdout
        # REFUSED, the closed port's own answer. The live NMAS gives "timed
        # out" from the laptop and a map on the host, so this is what fails if
        # the override is lost, on either machine.
        assert "Connection refused" in r.stderr, r.stderr   # the helper's own reason
        assert r.returncode == 2


class TestAFailedBackupStopsItsCopy:
    """C106 (2): the backup ran as `cp -r ... 2>/dev/null; rsync`, so a failed
    backup went on to overwrite the configs it protected. And a lab that
    failed was then blamed on the loop ("ran fewer times") and on the copy
    ("reported success ... do not match"), both false. The SHIPPED region,
    executed under bash against real directories, one lab's backup refused."""

    REGION = _between("ts=$(date +%Y%m%d-%H%M%S)\ntried_dests=0",
                      'match the staged copy."')

    def _run(self, tmp_path, fail_backup_of):
        stage = tmp_path / "stage"
        stage.mkdir()
        labs = {}
        for name in ("a", "b"):
            d = tmp_path / f"lab-{name}" / "configs"
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{name}.cfg").write_text("OLD\n")
            (stage / f"{name}.cfg").write_text("NEW\n")
            labs[name] = d
        refuse = str(labs[fail_backup_of]) if fail_backup_of in labs else "/nonexistent"
        script = f"""
set -uo pipefail
CLAB=clab; STAGE={str(stage)!r}
ssh() {{ local cmd="${{@: -1}}"
  if [[ "$cmd" == "cp -r '{refuse}'"* ]]; then echo "cp: Permission denied" >&2; return 1; fi
  bash -c "$cmd"; }}
# rsync is a network tool, refused under the harness (C46): a local copy of
# exactly the --files-from list stands in for it.
rsync() {{ local list src dst; list="${{2#--files-from=}}"; src="$3"; dst="$4"
  while read -r f; do [ -n "$f" ] && cp "$src/$f" "$dst/$f" || true; done < "$list"; }}
export -f rsync
declare -A CFGDIR
DEVICES=(a b)
CFGDIR[a]={str(labs['a'])!r}; CFGDIR[b]={str(labs['b'])!r}
destinations() {{ for n in "${{DEVICES[@]}}"; do echo "${{CFGDIR[$n]}}"; done | sort -u; }}
{self.REGION}
echo "COPIED=${{COPIED_DIRS[*]}}"
printf 'FAILED=%s\\n' "${{FAILED_DIRS[@]}}"
"""
        out = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                             env=_env(tmp_path), cwd=str(tmp_path))
        return out, labs

    def test_the_lab_whose_backup_failed_is_not_overwritten(self, tmp_path):
        out, labs = self._run(tmp_path, "b")
        assert (labs["b"] / "b.cfg").read_text() == "OLD\n", out.stdout + out.stderr
        assert (labs["a"] / "a.cfg").read_text() == "NEW\n"
        assert "BACKUP FAILED (cp: Permission denied)" in out.stdout
        assert "NOTHING was copied" in out.stdout

    def test_it_is_not_blamed_on_the_loop_or_the_copy(self, tmp_path):
        out, _labs = self._run(tmp_path, "b")
        assert "ran fewer times" not in out.stdout
        assert "NOT what was staged" not in out.stdout
        assert "Verified: all 1 file(s) in the 1 copied lab(s)" in out.stdout
        assert out.stdout.count("COPIED=") == 1 and "lab-a" in out.stdout.split("COPIED=")[1]


class TestALabThatCannotCommitIsNotCopied:
    """C106 (2), the second half: whether the commit can succeed was found
    AFTER the overwrite. The same shipped region, with lab b a repository
    holding a stale index.lock: refused before its copy, named."""

    def test_a_locked_repository_is_refused_before_its_copy(self, tmp_path):
        run = TestAFailedBackupStopsItsCopy()
        env = _env(tmp_path)
        repo = tmp_path / "lab-b"
        repo.mkdir()
        _git(env, "init", "-q", str(repo))
        (repo / ".git" / "index.lock").write_text("")
        out, labs = run._run(tmp_path, fail_backup_of="none-refused")
        assert (labs["b"] / "b.cfg").read_text() == "OLD\n", out.stdout + out.stderr
        assert (labs["a"] / "a.cfg").read_text() == "NEW\n"
        assert "CANNOT COMMIT" in out.stdout and "index.lock exists" in out.stdout
        assert "NOTHING was copied" in out.stdout


class TestOnlyAConfigurationChangeIsAChange:
    """C313 (the operator, 2026-10-01): every file began with
    `! <h> - from Oxidized HEAD <sha>`, so each Oxidized commit (any device's
    poll) changed all nine files by that line, and the sync reported, copied
    and committed every one ("! s1 - from Oxidized HEAD b1c29be" -> "fae137a").
    The SHIPPED comparison, executed under bash against real files."""

    COMPARE = _between("# >>> compare", "# <<< compare")

    def _run(self, tmp_path, current: dict, staged: dict, unreadable=()):
        lab = tmp_path / "lab" / "configs"
        lab.mkdir(parents=True)
        out = tmp_path / "out"
        out.mkdir()
        cur = tmp_path / "cur"
        cur.mkdir()
        for n, text in current.items():
            (lab / f"{n}.cfg").write_text(text)
        for n, text in staged.items():
            (out / f"{n}.cfg").write_text(text)
        decl = "\n".join(f"DEVICES+=({n!r}); CFGDIR[{n}]={str(lab)!r}; LAB[{n}]=default"
                         for n in staged)
        refuse = "|".join(unreadable) or "NONE"
        script = f"""
set -uo pipefail
CLAB=clab; STAGE=/nonexistent; OUT={str(out)!r}; CUR={str(cur)!r}
ssh() {{ local cmd="${{@: -1}}"
  if [[ "$cmd" =~ /({refuse})\\.cfg ]]; then return 255; fi
  bash -c "$cmd"; }}
declare -A CFGDIR LAB
DEVICES=()
{decl}
{_function("config_body")}
{self.COMPARE}
echo "COPY=${{COPY[*]}}"
"""
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                              env=_env(tmp_path), cwd=str(tmp_path))

    CONFIG = "hostname s1\ninterface Vlan1\n no ip address\n!\nend\n"

    def test_only_the_provenance_moved_is_unchanged_and_not_copied(self, tmp_path):
        old = "!\n! s1 - from Oxidized HEAD b1c29be\n!\n" + self.CONFIG
        r = self._run(tmp_path, {"s1": old}, {"s1": self.CONFIG})
        assert "s1   default          unchanged" in r.stdout, r.stdout + r.stderr
        assert "COPY=\n" in r.stdout

    def test_a_configuration_change_is_changed_and_copied(self, tmp_path):
        new = self.CONFIG.replace(" no ip address", " ip address 192.0.2.1 255.255.255.0")
        r = self._run(tmp_path, {"s1": "!\n! s1 - from Oxidized HEAD b1c29be\n!\n" + self.CONFIG,
                                 "s2": self.CONFIG.replace("s1", "s2")},
                      {"s1": new, "s2": self.CONFIG.replace("s1", "s2")})
        assert "s1   default          CHANGED  +1 / -1 lines" in r.stdout, r.stdout + r.stderr
        assert "s2   default          unchanged" in r.stdout
        assert "COPY=s1\n" in r.stdout

    def test_a_device_with_no_file_is_new_and_copied(self, tmp_path):
        r = self._run(tmp_path, {}, {"s1": self.CONFIG})
        assert "NEW - no current file" in r.stdout and "COPY=s1\n" in r.stdout

    def test_a_file_that_cannot_be_read_refuses_comparing_nothing(self, tmp_path):
        r = self._run(tmp_path, {"s1": self.CONFIG}, {"s1": self.CONFIG}, unreadable=("s1",))
        assert r.returncode == 1 and "could not be read" in r.stdout, r.stdout
        assert "COPY=" not in r.stdout

    def test_the_run_goes_on_with_only_the_files_that_move(self):
        tail = TEXT[TEXT.index("# <<< compare"):TEXT.index("# Back up, copy, verify, commit")]
        assert 'DEVICES=("${COPY[@]}")' in tail

    def test_render_device_writes_no_provenance(self):
        block = _function("render_device")
        assert "from Oxidized" not in block

    def test_the_lab_commit_names_the_source_commit_and_its_devices(self, tmp_path):
        d = _lab(tmp_path, "r6")
        (d / "r6.cfg").write_text("v2\n")
        r = _harness(tmp_path, {"r6": d}, COMMIT_BLOCK)
        assert f"{d}: committed" in r.stdout, r.stdout + r.stderr
        log = _git(_env(tmp_path), "-C", str(d.parent), "log", "-1", "--format=%s").stdout
        assert log.strip() == f"startup from {BASE_TAG} (now): r6"


class TestConfigBody:
    def _body(self, tmp_path, name, text):
        return subprocess.run(["bash", "-c", _function("config_body") + f"\nconfig_body {name}"],
                              input=text, capture_output=True, text=True,
                              env=_env(tmp_path)).stdout

    def test_a_pre_c313_header_is_dropped(self, tmp_path):
        assert self._body(tmp_path, "r1", "!\n! r1 - from Oxidized HEAD abc\n!\nhostname r1\n") \
            == "hostname r1\n"

    def test_a_file_with_no_header_is_unchanged(self, tmp_path):
        for text in ("!\nhostname r1\n!\nend\n", "hostname r1\n", "a\nb\n", ""):
            assert self._body(tmp_path, "r1", text) == text

    def test_another_devices_header_is_kept(self, tmp_path):
        text = "!\n! r2 - from Oxidized HEAD abc\n!\nhostname r1\n"
        assert self._body(tmp_path, "r1", text) == text


class TestTheFilesAreBuiltFromTheBaseline:
    """Plan item 4: the SHIPPED build loop, executed under bash. The source
    helper is a stub writing what `nmas-startup-source` writes (each device's
    file and sources.tsv); Oxidized is a real repository, read only for the
    cross-check."""

    BUILD = _between("# >>> build", "# <<< build")
    CROSS = _between("# >>> cross-check", "# <<< cross-check")

    def _run(self, tmp_path, sources: dict, oxidized: dict, tail=""):
        ox = tmp_path / "oxidized"
        for name, text in oxidized.items():
            ox, _sha = _oxidized(tmp_path, name, text)
        src = tmp_path / "src"
        src.mkdir()
        rows = [f"# baseline\t{BASE_TAG}\tabcdef0123456789"]
        for n, text in sources.items():
            if text is None:
                rows.append(f"{n}\trefused\t{BASE_TAG} holds no golden for {n}")
            else:
                (src / f"{n}.cfg").write_text(text)
                rows.append(f"{n}\tok\tcredentials from its current golden: accounts")
        tsv = "\\n".join(rows) + "\\n"
        stub = tmp_path / "source-stub"
        stub.write_text("#!/bin/bash\nout=$2\ncp " + str(src) + "/*.cfg \"$out\"/ 2>/dev/null\n"
                        "printf '" + tsv + "' > \"$out/sources.tsv\"\n")
        stub.chmod(0o755)
        out = tmp_path / "out"
        out.mkdir()
        decl = "\n".join(f"DEVICES+=({n!r}); NODE[{n}]={n!r}; PLATFORM[{n}]=cisco_iosxe"
                          for n in sources)
        script = f"""
set -uo pipefail
REF=HEAD; OUT={str(out)!r}; RAW={str(tmp_path / 'raw')!r}; SRCDIR={str(tmp_path / 'srcdir')!r}
SOURCE={str(stub)!r}
mkdir -p "$RAW" "$SRCDIR"
declare -A NODE PLATFORM
DEVICES=()
{decl}
GIT=(git -C {str(ox)!r})
{_function("kind_for")}
{_function("sanitise")}
{_function("render_device")}
{self.BUILD}
echo "DEVICES=${{DEVICES[*]}}"
echo "NOT_BUILT_LIST=$NOT_BUILT_LIST"
{tail}
"""
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                              env=_env(tmp_path), cwd=str(tmp_path))

    def test_each_file_is_the_baseline_s_render_and_a_device_it_lacks_is_not_built(self, tmp_path):
        r = self._run(tmp_path, {"r6": RUNNING, "r7": None}, {"r6": RUNNING})
        assert r.returncode == 0, r.stdout + r.stderr
        assert f"Building from {BASE_TAG} (abcdef0123)" in r.stdout
        assert f"NOT BUILT - {BASE_TAG} holds no golden for r7" in r.stdout
        assert "DEVICES=r6\n" in r.stdout and "NOT_BUILT_LIST=r7\n" in r.stdout
        assert (tmp_path / "out" / "r6.cfg").read_text().startswith("hostname r6")
        assert not (tmp_path / "out" / "r7.cfg").exists()

    def test_the_file_comes_from_the_baseline_not_from_oxidized(self, tmp_path):
        later = RUNNING.replace("ip address", "description changed by hand\n ip address")
        r = self._run(tmp_path, {"r6": RUNNING}, {"r6": later})
        assert r.returncode == 0, r.stdout + r.stderr
        assert "description changed by hand" not in (tmp_path / "out" / "r6.cfg").read_text()

    def test_the_cross_check_names_a_device_that_moved_and_never_blocks(self, tmp_path):
        later = RUNNING.replace("ip address", "description changed by hand\n ip address")
        r = self._run(tmp_path, {"r6": RUNNING}, {"r6": later}, tail=self.CROSS + "\necho DONE")
        assert r.returncode == 0 and "DONE" in r.stdout, r.stdout + r.stderr
        assert ("r6   DIFFERS from what runs now: it runs 1 line(s) the file lacks, and the "
                "file holds 0 it") in r.stdout
        assert f"does not. A redeploy boots {BASE_TAG}, not what r6 runs;" in r.stdout

    def test_the_cross_check_says_a_device_that_runs_its_file(self, tmp_path):
        r = self._run(tmp_path, {"r6": RUNNING}, {"r6": RUNNING}, tail=self.CROSS)
        assert "r6   runs what its file boots" in r.stdout, r.stdout + r.stderr

    def test_no_source_refuses_writing_nothing(self, tmp_path):
        stub = tmp_path / "fail-stub"
        stub.write_text("#!/bin/bash\necho 'UNPROVEN: Default has no earned baseline' >&2\nexit 2\n")
        stub.chmod(0o755)
        out = tmp_path / "out"
        out.mkdir()
        script = (f"set -uo pipefail\nREF=HEAD; OUT={str(out)!r}; SRCDIR={str(tmp_path)!r}; "
                  f"SOURCE={str(stub)!r}; DEVICES=(r6); GIT=(git)\n" + self.BUILD)
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                           env=_env(tmp_path), cwd=str(tmp_path))
        assert r.returncode == 2 and "no startup source could be built" in r.stdout
        assert "has no earned baseline" in r.stderr and list(out.iterdir()) == []
