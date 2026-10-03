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

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(ROOT, "scripts", "nmas-gate")
ENV = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="T", GIT_COMMITTER_EMAIL="t@example.com")


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
          extra=()):
    msg = tmp_path / "msg.txt"
    msg.write_text(f"{subject}\n\nThe suite: @SUITE@\n")
    env = dict(ENV, NMAS_GATE_SUITE=suite or _suite(["....", "12 passed, 1 skipped in 3.10s"]))
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

    def test_the_browser_tests_are_a_step_of_their_own(self, repo, tmp_path):
        r = _gate(repo, tmp_path, extra=("--browser",),
                  browser=_suite(["207 passed in 100.18s (0:01:40)"]))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "browser tests: 207 passed" in _git(repo, "log", "-1", "--format=%B")


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
        r = _gate(repo, tmp_path, subject="Plan: an older commit's subject", expect="Docs:",
                  suite="touch ran; " + _suite(["1 passed in 0.1s"]))
        assert r.returncode == 1 and "REFUSED at the message" in r.stdout
        assert not (repo / "ran").exists() and _commits(repo) == 1

    def test_a_failed_browser_run_refuses(self, repo, tmp_path):
        r = _gate(repo, tmp_path, extra=("--browser",),
                  browser=_suite(["1 failed, 206 passed in 99s"], rc=1))
        assert r.returncode == 1 and "REFUSED at the browser tests" in r.stdout
        assert _commits(repo) == 1

    def test_a_staged_secret_refuses_before_the_suite(self, repo, tmp_path):
        # Built by concatenation, so this file holds no key block the guard would refuse.
        (repo / "docs" / "server.key").write_text("-----BEGIN " + "PRIVATE KEY-----\nx\n")
        r = _gate(repo, tmp_path, suite="touch ran; " + _suite(["1 passed in 0.1s"]))
        assert r.returncode == 1 and "REFUSED at the stage guard" in r.stdout
        assert not (repo / "ran").exists() and _commits(repo) == 1

    def test_an_empty_expect_is_refused(self, repo, tmp_path):
        r = _gate(repo, tmp_path, expect=" ")
        assert r.returncode == 2 and _commits(repo) == 1


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
    env = text[text.index("name: Tests"):text.index("scripts/nmas-test", text.index("name: Tests"))]
    return cmd.split()[1:], dict(re.findall(r"(\w+): \"?([\w.]+)\"?", env.split("env:")[1]))


def test_the_default_suite_is_cis_command():
    """The gate's suite is CI's, read from the workflow itself (it pinned "-n 2" as CI's while
    CI ran `-n auto`, 2026-10-03): every argument CI passes, in CI's environment, with CI's
    runner's worker count for `auto`. Only the coverage REPORT differs (a terminal table)."""
    gate = _gate_module()
    args, env = _ci_suite_args()
    assert len(args) >= 8 and env, (args, env)
    suite = gate.SUITE.split()
    for a in args:
        if a == "auto":
            assert suite[suite.index("-n") + 1] == str(gate.CI_WORKERS)
        elif a.startswith("--cov-report"):
            assert any(s.startswith("--cov-report") for s in suite)
        else:
            assert a in suite, (a, gate.SUITE)
    for k, v in env.items():
        assert f"{k}={v}" in gate.SUITE, (k, v)


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
