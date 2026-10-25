"""`scripts/nmas-gate`, the commit gate as one program (the operator, 2026-10-02: five rules
about the gate lived only in CLAUDE.md and memory, each behind a past incident). Driven in
REAL temporary repositories, with the suite's command replaced (NMAS_GATE_SUITE) by one that
prints a chosen result:

- a passing run commits, with "@SUITE@" in the message replaced by the run's own last line
  (never a count written before the run, 71ed99e);
- a failure, an error, a non-zero exit, a last line that does not say what passed, and a run
  that never happened each refuse with NOTHING committed, naming the step and keeping the
  output (d0ce454, 195fdbe);
- a result file left by an EARLIER run is removed before this run, so a run that did not
  happen cannot pass on it (e986e66);
- a message whose first line is not this commit's refuses before the suite (df17b55, 17e9c7d);
- a secret staged refuses at the stage guard, before the suite;
- the browser tests are their own step with the same verdict.
"""

import os
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(ROOT, "scripts", "nmas-gate")
ENV = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="T", GIT_COMMITTER_EMAIL="t@example.com",
           # Each gate run here is a stand-in inside the real gate's suite: its full-suite lock
           # is its own (the real one is held by the gate running this test, 2026-10-19).
           NMAS_FULL_LOCK=os.path.join(tempfile.gettempdir(),
                                       f"nmas-gate-test-full-{os.getpid()}.lock"))


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=ENV, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "docs").mkdir(parents=True)
    _git(tmp_path, "init", "-q", str(r))
    (r / "docs" / "a.md").write_text("one\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    (r / "docs" / "a.md").write_text("two\n")
    return r


def _suite(lines, rc=0):
    """A shell command printing *lines* and exiting *rc*, standing in for the suite."""
    body = "; ".join(f"echo {line!r}" for line in lines)
    return f"{body}; exit {rc}"


def _gate(repo, tmp_path, *, subject="Docs: two", expect="Docs:", suite=None, browser=None,
          extra=(), ratchet=None):
    msg = tmp_path / "msg.txt"
    msg.write_text(f"{subject}\n\nThe suite: @SUITE@\n")
    env = dict(ENV, NMAS_GATE_SUITE=suite or _suite(["....", "12 passed, 1 skipped in 3.10s"]),
               NMAS_GATE_RATCHET=ratchet or _suite(["Tests that assert nothing: 0"]))
    if browser is not None:
        env["NMAS_GATE_BROWSER"] = browser
    return subprocess.run([sys.executable, GATE, "--repo", str(repo), "--message", str(msg),
                           "--expect", expect, *extra], capture_output=True, text=True, env=env)


def _commits(repo):
    return int(_git(repo, "rev-list", "--count", "HEAD"))


class TestAPassingRunCommits:
    def test_it_commits_with_the_runs_own_result_line(self, repo, tmp_path):
        r = _gate(repo, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        assert _commits(repo) == 2
        body = _git(repo, "log", "-1", "--format=%B")
        assert body.startswith("Docs: two")
        assert "The suite: 12 passed, 1 skipped in 3.10s" in body and "@SUITE@" not in body
        assert "1. git add -A" in r.stdout and "7. commit" in r.stdout

    def test_the_suite_runs_in_a_snapshot_and_the_working_tree_stays_free(self, repo, tmp_path):
        """The operator, 2026-10-25: the gate never locks the working tree. The suite runs in
        a snapshot of the staged tree; an edit made in the checkout DURING the run is not in
        the commit and is left as it was, uncommitted."""
        where = tmp_path / "where"
        r = _gate(repo, tmp_path, suite=(f"pwd > {where}; echo three > {repo / 'docs' / 'a.md'}; "
                                         + _suite(["12 passed in 1.00s"])))
        assert r.returncode == 0, r.stdout + r.stderr
        ran_in = where.read_text().strip()
        assert ran_in != str(repo) and "nmas-gate-snapshot-" in ran_in, ran_in
        assert _git(repo, "show", "HEAD:docs/a.md") == "two"           # the staged tree
        assert (repo / "docs" / "a.md").read_text() == "three\n"       # the edit, kept
        assert _git(repo, "status", "--porcelain") == "M docs/a.md"
        assert "2b. the snapshot" in r.stdout
        assert not os.path.exists(ran_in), "the snapshot was not removed"
        assert _git(repo, "worktree", "list").count("\n") == 0         # only the checkout

    def test_the_committed_tree_is_the_tested_one(self, repo, tmp_path):
        tree = None
        r = _gate(repo, tmp_path, suite=f"git write-tree > {tmp_path / 'tested'}; "
                                        + _suite(["12 passed in 1.00s"]))
        assert r.returncode == 0, r.stdout + r.stderr
        tree = (tmp_path / "tested").read_text().strip()
        assert _git(repo, "rev-parse", "HEAD^{tree}") == tree

    def test_a_hook_that_changes_the_commit_refuses_and_moves_nothing(self, repo, tmp_path):
        """A committed tree other than the tested one is refused: the branch does not move."""
        hooks = repo / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        hook = hooks / "pre-commit"
        hook.write_text("#!/bin/sh\necho extra > extra.txt && git add extra.txt\n")
        hook.chmod(0o755)
        before = _git(repo, "rev-parse", "HEAD")
        r = _gate(repo, tmp_path)
        assert r.returncode == 1 and "REFUSED at the commit" in r.stdout, r.stdout + r.stderr
        assert "is not the tested tree" in r.stdout
        assert _git(repo, "rev-parse", "HEAD") == before
        assert _git(repo, "worktree", "list").count("\n") == 0

    def test_a_branch_that_moved_during_the_run_refuses_and_keeps_it(self, repo, tmp_path):
        """Compare and swap: a commit put on the branch while the suite ran is kept, and the
        gate's commit is not put over it."""
        other = (f"git -C {repo} -c user.name=T -c user.email=t@example.com commit -q "
                 "--allow-empty -m other; ")
        r = _gate(repo, tmp_path, suite=other + _suite(["12 passed in 1.00s"]))
        assert r.returncode == 1 and "REFUSED at the branch" in r.stdout, r.stdout + r.stderr
        assert "moved during the run" in r.stdout
        assert _git(repo, "log", "-1", "--format=%s") == "other"
        assert _git(repo, "worktree", "list").count("\n") == 0

    def test_the_browser_tests_are_a_step_of_their_own(self, repo, tmp_path):
        r = _gate(repo, tmp_path, extra=("--browser",),
                  browser=_suite(["207 passed in 100.18s (0:01:40)"]))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "browser tests: 207 passed" in _git(repo, "log", "-1", "--format=%B")


class TestTheSnapshotNeverSurvives:
    """The operator, 2026-10-25: the snapshot holds `.env`, so it is owner-only (0700) and is
    removed on every exit: a pass, a refusal, an interrupt or a termination; one a killed gate
    left behind is removed by the next gate, and one a running gate owns is never touched."""

    @staticmethod
    def _snapshots():
        tmp = tempfile.gettempdir()
        return {n for n in os.listdir(tmp) if n.startswith("nmas-gate-snapshot-")
                and os.stat(os.path.join(tmp, n)).st_uid == os.getuid()}

    def _mode_and_folder(self, tmp_path):
        """A stand-in suite that records its snapshot's folder and that folder's mode."""
        return (f'p=$(dirname "$PWD"); echo "$p" > {tmp_path / "folder"}; '
                f'stat -c %a "$p" > {tmp_path / "mode"}; ')

    def test_owner_only_and_removed_after_a_pass(self, repo, tmp_path):
        r = _gate(repo, tmp_path, suite=self._mode_and_folder(tmp_path)
                                        + _suite(["12 passed in 1.00s"]))
        assert r.returncode == 0, r.stdout + r.stderr
        assert (tmp_path / "mode").read_text().strip() == "700"
        assert not os.path.exists((tmp_path / "folder").read_text().strip())

    def test_removed_after_a_refused_suite(self, repo, tmp_path):
        r = _gate(repo, tmp_path, suite=self._mode_and_folder(tmp_path)
                                        + _suite(["1 failed in 1s"], rc=1))
        assert r.returncode == 1 and "REFUSED at the suite" in r.stdout
        assert not os.path.exists((tmp_path / "folder").read_text().strip())

    @pytest.mark.parametrize("sig", ["INT", "TERM", "HUP"])
    def test_removed_after_an_interrupt_or_a_termination(self, repo, tmp_path, sig):
        """The suite signals the gate itself mid-run (Ctrl-C is SIGINT; a closed terminal,
        SIGHUP; a stop, SIGTERM), then waits to be killed with it."""
        suite = (self._mode_and_folder(tmp_path)
                 + f"kill -{sig} $PPID; sleep 30; " + _suite(["12 passed in 1.00s"]))
        r = _gate(repo, tmp_path, suite=suite)
        assert r.returncode != 0 and _commits(repo) == 1, r.stdout + r.stderr
        assert not os.path.exists((tmp_path / "folder").read_text().strip()), sig

    def test_a_snapshot_a_killed_gate_left_is_removed_and_a_live_one_kept(self, repo, tmp_path):
        """A folder whose gate is gone (here an owner that is not running) is removed by the
        next gate; one whose owner runs (this test's own process) is left alone."""
        tmp = tempfile.gettempdir()
        dead = tempfile.mkdtemp(prefix="nmas-gate-snapshot-", dir=tmp)
        live = tempfile.mkdtemp(prefix="nmas-gate-snapshot-", dir=tmp)
        try:
            with open(os.path.join(dead, "owner.pid"), "w") as fh:
                fh.write("999999999")
            with open(os.path.join(live, "owner.pid"), "w") as fh:
                fh.write(str(os.getpid()))
            r = _gate(repo, tmp_path)
            assert r.returncode == 0, r.stdout + r.stderr
            assert not os.path.exists(dead) and f"left behind: {dead}" in r.stdout
            assert os.path.exists(live)
        finally:
            import shutil
            shutil.rmtree(dead, ignore_errors=True)
            shutil.rmtree(live, ignore_errors=True)

    def test_an_ownerless_snapshot_is_kept_while_young_and_removed_once_old(self, repo,
                                                                          tmp_path):
        """2026-10-25: the first real snapshot run lost its snapshot mid-suite to a cleanup that
        judged a folder with no owner file (an earlier gate's) stale. Ownerless, it is kept
        while younger than the bound, and removed once older."""
        tmp = tempfile.gettempdir()
        young = tempfile.mkdtemp(prefix="nmas-gate-snapshot-", dir=tmp)
        old = tempfile.mkdtemp(prefix="nmas-gate-snapshot-", dir=tmp)
        try:
            os.utime(old, (1, 1))
            r = _gate(repo, tmp_path)
            assert r.returncode == 0, r.stdout + r.stderr
            assert os.path.exists(young) and not os.path.exists(old)
        finally:
            import shutil
            shutil.rmtree(young, ignore_errors=True)
            shutil.rmtree(old, ignore_errors=True)

    def test_no_snapshot_of_these_runs_survives(self, repo, tmp_path):
        """The floor for every test above: a pass and a refusal leave no folder of theirs."""
        before = self._snapshots()
        _gate(repo, tmp_path)
        _gate(repo, tmp_path, suite=_suite(["1 failed in 1s"], rc=1))
        assert self._snapshots() - before == set()


class TestEveryWayAStepFails:
    @pytest.mark.parametrize("suite,why", [
        (_suite(["FAILED tests/test_x.py::test_y - assert 1 == 2",
                 "1 failed, 11 passed in 3.1s"], rc=1), "exited 1"),
        (_suite(["ERROR tests/test_x.py - ImportError", "11 passed, 1 error in 3.1s"]),
         "a failure or error is reported"),
        (_suite(["11 passed in 3.1s"], rc=2), "exited 2"),
        (_suite(["Killed"]), "does not say what passed"),
        ("exit 0", "does not say what passed"),
    ], ids=["failed", "error_with_rc0", "nonzero_exit", "no_verdict_line", "no_output"])
    def test_a_run_that_did_not_pass_commits_nothing_and_keeps_its_output(self, repo, tmp_path,
                                                                          suite, why):
        r = _gate(repo, tmp_path, suite=suite)
        assert r.returncode == 1 and "REFUSED at the suite" in r.stdout and why in r.stdout
        assert _commits(repo) == 1
        assert "nmas-gate-suite.out" in r.stdout          # where the whole output is kept

    def test_an_earlier_runs_result_is_never_read(self, repo, tmp_path):
        """e986e66: the run was skipped and the gate read the PREVIOUS run's pass."""
        gitdir = _git(repo, "rev-parse", "--absolute-git-dir")
        with open(os.path.join(gitdir, "nmas-gate-suite.out"), "w") as fh:
            fh.write("5330 passed in 60.0s\n")
        # A run that exits 0 and writes nothing of its own: only the earlier file could pass it.
        # (A non-zero exit would be refused on the status and test nothing about the file.)
        r = _gate(repo, tmp_path, suite="true")
        assert r.returncode == 1 and "REFUSED at the suite" in r.stdout
        assert "5330 passed" not in r.stdout and _commits(repo) == 1

    def test_a_message_that_is_not_this_commits_refuses_before_the_suite(self, repo, tmp_path):
        # The stand-in marks an ABSOLUTE path: the suite runs in the gate's snapshot, not in
        # the checkout, so a relative mark would never be where this looks.
        r = _gate(repo, tmp_path, subject="Plan: an older commit's subject", expect="Docs:",
                  suite=f"touch {tmp_path / 'ran'}; " + _suite(["1 passed in 0.1s"]))
        assert r.returncode == 1 and "REFUSED at the message" in r.stdout
        assert not (tmp_path / "ran").exists() and _commits(repo) == 1

    def test_a_failed_browser_run_refuses(self, repo, tmp_path):
        r = _gate(repo, tmp_path, extra=("--browser",),
                  browser=_suite(["1 failed, 206 passed in 99s"], rc=1))
        assert r.returncode == 1 and "REFUSED at the browser tests" in r.stdout
        assert _commits(repo) == 1

    def test_a_staged_secret_refuses_before_the_suite(self, repo, tmp_path):
        # Built by concatenation, so this file holds no key block the guard would refuse.
        (repo / "docs" / "server.key").write_text("-----BEGIN " + "PRIVATE KEY-----\nx\n")
        r = _gate(repo, tmp_path, suite=f"touch {tmp_path / 'ran'}; "
                                        + _suite(["1 passed in 0.1s"]))
        assert r.returncode == 1 and "REFUSED at the stage guard" in r.stdout
        assert not (tmp_path / "ran").exists() and _commits(repo) == 1

    def test_an_empty_expect_is_refused(self, repo, tmp_path):
        r = _gate(repo, tmp_path, expect=" ")
        assert r.returncode == 2 and _commits(repo) == 1


class TestTheCoverageRatchet:
    """C808 (the operator's decision, 2026-10-15): the gate ran the suite with coverage but not
    the ratchet, so it passed and CI's coverage job failed after the push. Step 4b runs CI's
    ratchet over the four shards' measurement; measured to add under 30 s (docs/TESTING.md,
    "Where it runs")."""

    FAILED = _suite(["Combined 4 files", "Tests that assert nothing: 0", "",
                     "THE RATCHET:",
                     "  modules/x.py: uncovered functions rose from 1 (2 of 3 covered) to "
                     "2 (2 of 4 covered)"], rc=1)

    def test_a_ratchet_failure_refuses_naming_the_module_and_both_figures(self, repo, tmp_path):
        r = _gate(repo, tmp_path, ratchet=self.FAILED)
        assert r.returncode == 1 and "REFUSED at the coverage ratchet" in r.stdout
        assert ("modules/x.py: uncovered functions rose from 1 (2 of 3 covered) to "
                "2 (2 of 4 covered)") in r.stdout
        assert "nmas-gate-ratchet.out" in r.stdout and _commits(repo) == 1

    def test_a_ratchet_that_fails_before_judging_refuses_with_its_last_line(self, repo,
                                                                            tmp_path):
        r = _gate(repo, tmp_path, ratchet=_suite(["No data to combine"], rc=1))
        assert r.returncode == 1 and "REFUSED at the coverage ratchet" in r.stdout
        assert "before judging" in r.stdout and "No data to combine" in r.stdout
        assert _commits(repo) == 1

    def test_a_holding_ratchet_commits(self, repo, tmp_path):
        r = _gate(repo, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "4b. the coverage ratchet holds" in r.stdout and _commits(repo) == 2

    def test_it_runs_only_after_the_suite_passed(self, repo, tmp_path):
        r = _gate(repo, tmp_path, suite=_suite(["1 failed, 11 passed in 3.1s"], rc=1),
                  ratchet="touch ratchet-ran; " + _suite(["ok"]))
        assert r.returncode == 1 and "REFUSED at the suite" in r.stdout
        assert not (repo / "ratchet-ran").exists()

    def test_an_earlier_runs_measurement_is_never_read(self, repo, tmp_path):
        """Step 3's rule for the measurement: a shard that wrote nothing cannot be judged on
        an earlier run's data file."""
        gitdir = _git(repo, "rev-parse", "--absolute-git-dir")
        stale = os.path.join(gitdir, "nmas-gate-coverage", ".coverage.a")
        os.makedirs(os.path.dirname(stale))
        open(stale, "w").close()
        r = _gate(repo, tmp_path, ratchet=f"test ! -e {stale} && echo fresh")
        assert r.returncode == 0, r.stdout + r.stderr

    def test_the_ratchet_is_cis_coverage_job(self):
        """The default command is CI's: the four shards combined, then the report with --check
        over the tier records (ci.yml's coverage job, read from the workflow)."""
        import yaml
        gate = _gate_module()
        doc = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "ci.yml"),
                                  encoding="utf-8"))
        steps = doc["jobs"]["coverage"]["steps"]
        combine = next(s["run"] for s in steps if s.get("name") == "Combine them")
        report = " ".join(next(s["run"] for s in steps
                               if s.get("name") == "The report and the ratchet").split())
        assert "coverage combine --keep --data-file=.coverage" in combine
        assert "coverage combine --keep --data-file={cov}/.coverage {files}" in gate.RATCHET
        assert "scripts/nmas-coverage report --data .coverage --tiers tiers" in report
        assert "--check" in report.split()
        assert ("scripts/nmas-coverage report --data {cov}/.coverage --tiers {cov}/tiers --check"
                in gate.RATCHET)
        shard = gate.SUITE.format(py="P", shard="a", cov="D", n=4, bound=740)
        assert "COVERAGE_FILE=D/.coverage.a" in shard and "NMAS_TEST_TIERS=D/tiers" in shard


def _gate_module():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("nmas_gate", GATE)
    spec = importlib.util.spec_from_loader("nmas_gate", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _ci_suite_args():
    """CI's own test command, read from the workflow: every argument after nmas-test, its
    environment, and its worker count."""
    import re
    text = open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8").read()
    step = text[text.index("scripts/nmas-test", text.index("name: Tests")):]
    cmd = " ".join(step[:step.index("\n\n")].split())
    # The job's shard of the files is compared on its own (test_each_job_is_a_gate_command).
    cmd = re.sub(r"\$\(python scripts/nmas-shards \$\{\{ matrix\.shard \}\}\)", "", cmd)
    cmd = cmd.replace("${{ matrix.shard }}", "{shard}")
    env = text[text.index("name: Tests"):text.index("scripts/nmas-test", text.index("name: Tests"))]
    return cmd.split()[1:], dict(re.findall(r"(\w+): \"?([\w.]+)\"?", env.split("env:")[1]))


#: What CI passes and the gate deliberately does not. Since C773 (2026-10-14) a push measures by
#: tier with sys.monitoring and no per-test argument (the per-test measurement is the nightly
#: coverage run's), so nothing: the gate runs CI's command argument for argument.
CI_ONLY_ARGS = ()
#: CI's own bound (2.5x ITS measured step, 1470 s; the gate's stays 740 s, derived for its own
#: run), and the coverage job's two inputs whose VALUES are paths of CI's workspace: the gate
#: sets both in its own folder (test_the_ratchet_is_cis_coverage_job). Since C808 the gate
#: measures by tier as CI does (NMAS_COVERAGE_TIERS=1) and runs the ratchet (step 4b).
CI_ONLY_ENV = ("COVERAGE_FILE", "NMAS_TEST_TIERS", "NMAS_TEST_TIMEOUT")


def test_the_default_suite_is_cis_command():
    """The gate's suite is CI's, read from the workflow itself (it pinned "-n 2" as CI's while
    CI ran `-n auto`, 2026-10-03): every argument CI passes, in CI's environment, with CI's
    runner's worker count for `auto`. Only the coverage REPORT differs (a terminal table), and
    the per-test measurement CI alone takes (CI_ONLY_ARGS, CI_ONLY_ENV)."""
    gate = _gate_module()
    args, env = _ci_suite_args()
    assert len(args) >= 8 and env, (args, env)
    assert set(CI_ONLY_ARGS) <= set(args), "the exemption names what CI really passes"
    suite = gate.SUITE.split()
    for a in args:
        if a == "auto":
            # CI's runner's count, as a CEILING: each shard's workers come from the memory
            # available when the gate runs (the operator, 2026-10-19; tests/test_nmas_workers.py),
            # never more than CI's CI_WORKERS, whatever the memory.
            assert suite[suite.index("-n") + 1] == "{n}"
            assert gate.suite_workers(10 ** 15)[0] == gate.CI_WORKERS
            assert gate.suite_workers(0)[0] == 1
        elif a.startswith("--cov-report"):
            assert any(s.startswith("--cov-report") for s in suite)
        elif a.startswith("--junitxml="):
            # Its value is a path of CI's workspace (C1637): the gate writes the same file,
            # per shard, in its own folder, as it does COVERAGE_FILE.
            assert a == "--junitxml=junit-{shard}.xml", a
            assert "--junitxml={cov}/junit-{shard}.xml" in suite, gate.SUITE
        elif a not in CI_ONLY_ARGS:
            assert a in suite, (a, gate.SUITE)
    for k, v in env.items():
        if k not in CI_ONLY_ENV:
            assert f"{k}={v}" in gate.SUITE, (k, v)


def test_each_job_is_a_gate_command():
    """CI runs the suite as a matrix of jobs, each its shard (`scripts/nmas-shards`); the gate
    runs the SAME shards, each with the same selector, at once (2026-10-03, C349's parity)."""
    import yaml
    gate = _gate_module()
    doc = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "ci.yml"),
                              encoding="utf-8"))
    job = doc["jobs"]["test"]
    # The matrix is the scope job's (the operator, 2026-10-25): the gate's five for any change
    # outside docs/, the gate's doc job for a docs-only one, read from nmas-shards, the one rule.
    assert job["needs"] == "scope"
    assert job["strategy"]["matrix"]["shard"] == "${{ fromJSON(needs.scope.outputs.shards) }}"
    shards = _shards_module()
    assert tuple(shards.matrix(["modules/redact.py", "docs/a.md"])) == gate.SHARDS
    assert tuple(shards.matrix(None)) == gate.SHARDS, "an unreadable range runs everything"
    assert shards.matrix(["docs/a.md", "docs/OPEN_FINDINGS.md"]) == [gate.DOC_SHARD]
    assert job["strategy"].get("fail-fast") is False, "every job reports, a failure or not"
    tests = next(s for s in job["steps"] if str(s.get("name", "")).startswith("Tests"))
    assert "$(python scripts/nmas-shards ${{ matrix.shard }})" in tests["run"]
    assert "scripts/nmas-shards {shard})" in gate.SUITE
    for s in gate.SHARDS:
        assert gate.SUITE.format(py="P", shard=s, cov="D", n=4, bound=740).endswith(
            f"$(P scripts/nmas-shards {s})")
    once = [s for s in job["steps"]
            if s.get("if") == "matrix.shard == 'a' || matrix.shard == 'docs'"]
    assert {s["name"][:20] for s in once} == {"No removed definitio", "Every host-installed",
                                              "Every weakened test "}
    cov = doc["jobs"]["coverage"]
    assert cov["needs"] == ["scope", "test"]
    assert cov["if"] == "${{ !cancelled() && needs.scope.outputs.docs_only != 'true' }}"


def _shards_module():
    import importlib.machinery
    import importlib.util
    path = os.path.join(ROOT, "scripts", "nmas-shards")
    loader = importlib.machinery.SourceFileLoader("nmas_shards_for_gate_test", path)
    spec = importlib.util.spec_from_loader("nmas_shards_for_gate_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class TestADocsOnlyCommit:
    """The operator, 2026-10-25: a tree whose every changed path is under docs/ runs the doc
    set alone (tests/doc_tests.py) and not the ratchet; any other path runs everything."""

    @pytest.fixture
    def ruled(self, repo):
        """The fixture's repository with the real rule (tests/doc_tests.py) committed in it."""
        (repo / "tests").mkdir()
        with open(os.path.join(ROOT, "tests", "doc_tests.py"), encoding="utf-8") as fh:
            (repo / "tests" / "doc_tests.py").write_text(fh.read())
        _git(repo, "add", "tests/doc_tests.py")
        _git(repo, "commit", "-q", "-m", "the rule")
        return repo

    def test_a_docs_only_tree_skips_the_ratchet_and_says_why(self, ruled, tmp_path):
        r = _gate(ruled, tmp_path, ratchet="echo 'ratchet ran' > " + str(tmp_path / "rat")
                                           + "; exit 1")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "4. docs only: every one of the 1 changed path(s) is under docs/" in r.stdout
        assert "4b. the coverage ratchet: not run, docs only" in r.stdout
        assert not (tmp_path / "rat").exists()

    def test_a_tree_touching_anything_else_runs_the_ratchet(self, ruled, tmp_path):
        (ruled / "tests" / "test_x.py").write_text("x = 1\n")
        r = _gate(ruled, tmp_path, ratchet="echo 'ratchet ran' > " + str(tmp_path / "rat")
                                           + "; echo 'Tests that assert nothing: 0'")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "docs only" not in r.stdout and (tmp_path / "rat").exists()


def test_the_four_jobs_run_at_once_and_each_is_judged(repo, tmp_path, monkeypatch):
    """Each job's result file is its own and is judged alone: one job failing refuses, naming
    it, whatever the others said."""
    gate = _gate_module()
    runs = {s: (f"echo '{'1 failed, ' if s == 'b' else ''}3 passed in 0.10s'",
                str(tmp_path / f"{s}.out")) for s in gate.SHARDS}
    codes = gate.run_all_to_files(runs, str(repo), dict(os.environ))
    assert set(codes) == set(gate.SHARDS)
    whys = {s: gate.verdict(path, codes[s]) for s, (_c, path) in runs.items()}
    assert gate.SHARDS == ("browser1", "browser2", "browser3", "a", "b")
    assert not any(whys[s] for s in ("browser1", "browser2", "browser3", "a")) and whys["b"]


def test_a_browser_test_skipped_in_the_suite_refuses(repo, tmp_path):
    """CI's runner starts a browser inside the confinement; a local suite whose browser tests
    SKIPPED is not CI's run, and from ca52963 to 64d4377 that is how CI's red went unseen."""
    r = _gate(repo, tmp_path, suite=_suite([
        "SKIPPED [3] tests/test_attention_badge.py:192: no real browser here (no firefox)",
        "12 passed, 3 skipped in 3.10s"]))
    assert r.returncode == 1 and "REFUSED at the suite" in r.stdout
    assert "browser test skip" in r.stdout and _commits(repo) == 1


def test_every_browser_test_skips_in_the_words_the_gate_refuses():
    """The refusal reads one phrase; a browser test skipping in other words would pass a gate
    that never ran it. Population: every test file that asks `browser.available()`."""
    import re
    phrase = _gate_module().BROWSER_SKIPPED
    users = []
    for name in sorted(os.listdir(os.path.join(ROOT, "tests"))):
        if not name.endswith(".py"):
            continue
        text = open(os.path.join(ROOT, "tests", name), encoding="utf-8").read()
        if re.search(r"=\s*browser\.available\(\)", text):
            users.append(name)
            skips = re.findall(r"pytest\.skip\(f?\"([^\"]*)", text)
            about = [s for s in skips if re.search(r"(?i)browser|firefox|gecko", s)]
            assert about and all(s.startswith(phrase) for s in about), (name, skips)
    assert len(users) >= 7, users


class TestCIsInterpreterHoldsWhatCIInstalls:
    """C594 (CI #537, 2026-10-09): the lock gained boto3, the gate's interpreter never did, and
    CI went red on what the gate had not run. The gate compares its interpreter's packages
    with the three files CI installs before the suite, and refuses a difference by name."""

    def _world(self, tmp_path, listed):
        for name, text in (("requirements.lock", "# a lock\nboto3==1.34.46\nFlask==3.0.2\n"),
                           ("requirements-ci.txt", "coverage==7.16.1\n"),
                           ("requirements-test.txt", "pytest-xdist==3.8.0\n")):
            (tmp_path / name).write_text(text, encoding="utf-8")
        py = tmp_path / "python"
        py.write_text("#!/bin/sh\ncat <<'EOF'\n" + "\n".join(listed) + "\nEOF\n", encoding="utf-8")
        py.chmod(0o755)
        return str(py), str(tmp_path)

    def test_a_matching_interpreter_has_no_difference(self, tmp_path):
        gate = _gate_module()
        py, repo = self._world(tmp_path, ["boto3==1.34.46", "flask==3.0.2", "coverage==7.16.1",
                                          "pytest_xdist==3.8.0", "pip==24.0"])
        assert gate.interpreter_differs(py, repo) == []

    def test_a_missing_and_a_moved_package_are_each_named(self, tmp_path):
        gate = _gate_module()
        py, repo = self._world(tmp_path, ["flask==3.0.3", "coverage==7.16.1",
                                          "pytest-xdist==3.8.0"])
        assert gate.interpreter_differs(py, repo) == [
            "boto3==1.34.46 is not installed", "Flask is 3.0.3, CI installs 3.0.2"]

    def test_the_gate_refuses_before_the_suite(self, repo, tmp_path):
        """The refusal runs the real gate against a planted interpreter missing a pin."""
        (tmp_path / "py").mkdir()
        py, planted = self._world(tmp_path / "py", ["flask==3.0.2"])
        for name in ("requirements.lock", "requirements-ci.txt", "requirements-test.txt"):
            (repo / name).write_text((tmp_path / "py" / name).read_text(encoding="utf-8"),
                                     encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "CI's three files")
        (repo / "docs" / "a.md").write_text("three\n")
        msg = tmp_path / "msg.txt"
        msg.write_text("Docs: two\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "NMAS_GATE_SUITE"}
        r = subprocess.run([sys.executable, GATE, "--message", str(msg), "--expect", "Docs:",
                            "--repo", repo, "--python", py], capture_output=True, text=True,
                           env=env, timeout=60)
        assert r.returncode != 0
        assert "REFUSED at CI's interpreter" in r.stdout + r.stderr
        assert "boto3==1.34.46 is not installed" in r.stdout + r.stderr
        assert "the suite" not in (r.stdout + r.stderr).split("REFUSED")[0].split("3. ")[-1], \
            "it refuses before any suite runs"


class TestNothingIsPushedOnARedCi:
    """C791 (2026-10-15): three commits were pushed onto CI #791's red, the run never read.
    With --push the gate first reads CI's newest verdict on main (`nmas-ci-log main-ci`,
    replaced here by NMAS_GATE_CI_LOG) and refuses on red, naming the run, before anything is
    staged; the commit fixing it forward names that run with --fixes-red."""

    @pytest.fixture
    def pushing(self, repo, tmp_path):
        origin = tmp_path / "origin.git"
        _git(tmp_path, "init", "-q", "--bare", str(origin))
        _git(repo, "remote", "add", "origin", str(origin))
        _git(repo, "push", "-q", "-u", "origin", "HEAD")
        return origin

    @staticmethod
    def _verdict(state, n=791, rc=None):
        line = ('{"state": "%s", "run": {"run_number": %d, "head_sha": "5e7c0632e", '
                '"conclusion": "failure", "html_url": "https://ci.example/%d"}}' % (state, n, n))
        return f"echo '{line}'; exit {rc if rc is not None else (0 if state == 'green' else 3)}"

    def _run(self, repo, tmp_path, ci, *extra):
        msg = tmp_path / "msg.txt"
        msg.write_text("Docs: two\n")
        env = dict(ENV, NMAS_GATE_SUITE=_suite(["12 passed in 1.00s"]), NMAS_GATE_CI_LOG=ci,
                   NMAS_GATE_RATCHET=_suite(["Tests that assert nothing: 0"]))
        return subprocess.run([sys.executable, GATE, "--repo", str(repo), "--message", str(msg),
                               "--expect", "Docs:", "--push", *extra], capture_output=True,
                              text=True, env=env)

    def test_green_pushes(self, repo, tmp_path, pushing):
        r = self._run(repo, tmp_path, self._verdict("green", 802))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "CI on main is green: #802" in r.stdout
        assert _git(pushing, "log", "-1", "--format=%s") == "Docs: two"

    def test_red_refuses_naming_the_run_and_stages_nothing(self, repo, tmp_path, pushing):
        before = _commits(repo)
        r = self._run(repo, tmp_path, self._verdict("red"))
        out = r.stdout + r.stderr
        assert r.returncode == 1
        assert "REFUSED at CI on main: CI on main is red: #791" in out
        assert "https://ci.example/791" in out and "--fixes-red 791" in out
        assert "1. git add -A" not in out and _commits(repo) == before
        assert _git(repo, "diff", "--cached", "--name-only") == ""
        assert _git(pushing, "log", "-1", "--format=%s") == "base"

    def test_the_fix_forward_names_that_very_run(self, repo, tmp_path, pushing):
        r = self._run(repo, tmp_path, self._verdict("red"), "--fixes-red", "790")
        assert r.returncode == 1 and "--fixes-red 790 names another run" in r.stdout
        r = self._run(repo, tmp_path, self._verdict("red"), "--fixes-red", "791")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "fixes it forward" in r.stdout
        assert _git(pushing, "log", "-1", "--format=%s") == "Docs: two"

    def test_an_unreadable_verdict_refuses(self, repo, tmp_path, pushing):
        r = self._run(repo, tmp_path, "echo 'nmas-ci-log: GitHub could not be asked' >&2; exit 2")
        assert r.returncode == 1
        assert "CI's verdict on main could not be read" in r.stdout
        assert "GitHub could not be asked" in r.stdout

    def test_without_push_ci_is_not_asked(self, repo, tmp_path):
        msg = tmp_path / "msg.txt"
        msg.write_text("Docs: two\n")
        env = dict(ENV, NMAS_GATE_SUITE=_suite(["12 passed in 1.00s"]),
                   NMAS_GATE_RATCHET=_suite(["Tests that assert nothing: 0"]),
                   NMAS_GATE_CI_LOG="echo asked > " + str(tmp_path / "asked"))
        r = subprocess.run([sys.executable, GATE, "--repo", str(repo), "--message", str(msg),
                            "--expect", "Docs:"], capture_output=True, text=True, env=env)
        assert r.returncode == 0 and not (tmp_path / "asked").exists()
