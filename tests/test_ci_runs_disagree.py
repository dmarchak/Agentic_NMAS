"""C3425: the running commit's CI row when runs on one commit disagree (the operator,
2026-11-13, on 4f20f7b9cf: #1679 passed and the host ran it; main's own run #1680 failed on a
runner's Firefox running out of memory, C3020, and was re-run).

The operator's three fixes: "1. Severity WARNING, not critical (critical = a network outage;
this notice was designed as a warning). 2. When runs on the same sha disagree (#1679 passed,
#1680 failed), say so: list both, name the failed job and test, say whether a re-run is in
progress. Never "Do not deploy this commit" for a commit already running with a pass. 3. What
to do: "Re-run the failed job" (or "nothing: a re-run is running"), not "Update…" when no newer
release exists. Also, its start time is knowable (#1680's completion), so not "start not
tracked"."

Every state is driven through the real reader (`ci_verdict.read`, which runs `nmas-deploy`'s
own `ci_verdict()`) and a GitHub answering from REAL captures of that commit's runs, #1680
attempt 1's jobs and its failed job's annotations (tests/fixtures/github/runs_1680_rerun.json,
2026-11-13, the account a placeholder). The one typed state is attempt 2 while it ran: the
captured attempt 2 with its status put back to `in_progress` and no conclusion (GitHub's
listing shows a run's latest attempt; it had passed by the capture).
"""

import copy
import dataclasses
import json
import os
import subprocess

import pytest

from modules import attention as A
from modules import config
from modules import reader_job as R
from modules.readers import ci_verdict as CV
from routes import health

HERE = os.path.dirname(os.path.abspath(__file__))
SLUG = "account/Agentic_NMAS"
with open(os.path.join(HERE, "fixtures", "github", "runs_1680_rerun.json"), encoding="utf-8") as fh:
    FIX = json.load(fh)
RUN_ID = FIX["run_1680_attempt_1"]["id"]
URL_1680 = FIX["run_1680_attempt_1"]["html_url"]
BROWSER3 = next(j for j in FIX["jobs_1680_attempt_1"]["jobs"] if j["conclusion"] == "failure")
TEST = ("tests/test_htmx_form_never_posted_natively.py::"
        "test_a_press_before_htmx_has_loaded_is_kept_and_sent_once_it_has")
#: #1680 attempt 1's completion: the run's `updated_at` in its /attempts/1 capture.
FAILED_AT = "2026-11-13T05:47:54Z"
T0 = 1_794_000_000.0


def _git(cwd, *args):
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True,
                         env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                                  GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com"))
    return out.stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A checkout with a GitHub-shaped origin (nothing is fetched), running its tip."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "checkout"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
    (root / "f").write_text("1")
    _git(root, "add", "f")
    _git(root, "commit", "-q", "-m", "c1")
    tip = _git(root, "rev-parse", "HEAD")
    monkeypatch.setattr(health, "_COMMIT", tip)
    return {"root": str(root), "tip": tip, "store": {"path": str(tmp_path / "no-local-ci"),
                                                     "owner": 0}}


def _rerunning():
    run = dict(FIX["run_1680_attempt_2"], status="in_progress", conclusion=None)
    return run


RUNS = {
    "failed": [FIX["run_1679"], FIX["run_1680_attempt_1"]],
    "rerunning": [FIX["run_1679"], _rerunning()],
    "rerun_passed": [FIX["run_1679"], FIX["run_1680_attempt_2"]],
    "alone": [FIX["run_1680_attempt_1"]],
    "rerun_failed": [FIX["run_1679"], dict(FIX["run_1680_attempt_2"], conclusion="failure")],
}


class GitHub:
    """GitHub's public API as captured: the commit's runs for *state*, #1680's jobs and the
    failed job's annotations; any other commit has no run. Every path asked is kept."""

    def __init__(self, tip):
        self.tip, self.state, self.asked = tip, "failed", []

    def __call__(self, path, *args, **kwargs):
        self.asked.append(path)
        if "/actions/runs?" in path:
            runs = RUNS[self.state] if f"head_sha={self.tip}" in path else []
            return 200, {"workflow_runs": copy.deepcopy(runs)}, ""
        if path.startswith(f"/repos/{SLUG}/actions/runs/{RUN_ID}/jobs"):
            return 200, copy.deepcopy(FIX["jobs_1680_attempt_1"]), ""
        if path.startswith(f"/repos/{SLUG}/check-runs/{BROWSER3['id']}/annotations"):
            return 200, copy.deepcopy(FIX["annotations_1680_attempt_1_browser3"]), ""
        pytest.fail(f"asked GitHub for {path}")


@pytest.fixture
def github(repo):
    return GitHub(repo["tip"])


def _read(repo, github, state, previous=None):
    github.state = state
    return CV.read(commit=repo["tip"], get=github, previous=previous or {}, root=repo["root"],
                   store=repo["store"],
                   fetch=lambda _root: ("absent", "origin holds no refs/notes/nmas-gate"))


def _cached(value):
    return {"state": "ok", "doc": {"last_good": {"value": value,
                                                 "value_at": "2026-11-13T06:20:00Z"},
                                   "stale_after_seconds": 1800}}


def _pushed(repo, target=None):
    """The app-pushed reader's stored value: at the tip, or behind a *target* CI passed."""
    v = {"running": repo["tip"], "state": "at_tip", "tip": repo["tip"]}
    if target:
        v.update(state="behind", tip=target, target=target,
                 verdicts={target: {"state": "verified"}})
    return _cached(v)


def _rows(repo, value, target=None):
    return A.ci_source(cached=_cached(value), pushed=_pushed(repo, target))["rows"]


# ---------------------------------------------------------------- #1680 attempt 1 failed

class TestTheDisagreement:
    def test_it_is_a_warning_never_critical(self, repo, github):
        (row,) = _rows(repo, _read(repo, github, "failed"))
        assert row["level"] == "warning"

    def test_it_says_the_runs_disagree_and_lists_both(self, repo, github):
        v = _read(repo, github, "failed")
        assert v["state"] == "failed"
        (row,) = _rows(repo, v)
        assert row["what"] == (f"The running commit {repo['tip'][:10]}: its CI runs disagree, "
                               "#1679 passed and #1680 failed"), row["what"]
        assert "#1679 attempt 1 passed; #1680 attempt 1 failed" in row["cause"], row["cause"]

    def test_it_names_the_failed_job_and_test(self, repo, github):
        (row,) = _rows(repo, _read(repo, github, "failed"))
        assert "in test (browser3)" in row["cause"]
        assert (f"in test (browser3): {TEST} (urllib.error.HTTPError: HTTP Error 500"
                in row["cause"]), row["cause"]

    def test_it_says_no_re_run_is_running(self, repo, github):
        (row,) = _rows(repo, _read(repo, github, "failed"))
        assert "No re-run is running." in row["cause"]

    def test_never_do_not_deploy_nor_the_deploy_sentence_whole(self, repo, github):
        v = _read(repo, github, "failed")
        assert "Do not deploy this commit." in v["sentence"]     # the deploy tool's, kept stored
        (row,) = _rows(repo, v)
        text = json.dumps(row)
        assert "Do not deploy" not in text
        assert "FAILED: CI's latest conclusive run" not in text
        assert v["sentence"] not in row["cause"]

    def test_its_action_is_the_re_run_of_the_failed_job_linking_the_run(self, repo, github):
        (row,) = _rows(repo, _read(repo, github, "failed"))
        assert row["action"]["label"].startswith("Re-run the failed job"), row["action"]
        assert row["action"]["run_url"] == URL_1680 and row["action"]["run"] == "1680"
        assert "open" not in row["action"]

    def test_update_only_when_a_newer_release_ci_passed_exists(self, repo, github):
        v = _read(repo, github, "failed")
        newer = "b" * 40
        (row,) = _rows(repo, v, target=newer)
        assert row["action"]["open"] == "app_update"
        assert row["action"]["label"].startswith(f"Update to {newer[:7]}"), row["action"]
        (row,) = A.ci_source(cached=_cached(v), pushed={"state": "absent", "doc": None,
                                                         "why": "never"})["rows"]
        assert "open" not in row["action"]

    def test_since_is_the_failed_runs_completion(self, repo, github):
        (row,) = _rows(repo, _read(repo, github, "failed"))
        assert row["since"] == FAILED_AT

    def test_where_it_failed_is_asked_once_per_failed_attempt(self, repo, github):
        first = _read(repo, github, "failed")
        jobs = [p for p in github.asked if "/jobs" in p or "/annotations" in p]
        assert jobs == [f"/repos/{SLUG}/actions/runs/{RUN_ID}/jobs?per_page=50",
                        f"/repos/{SLUG}/check-runs/{BROWSER3['id']}/annotations?per_page=50"]
        github.asked.clear()
        again = _read(repo, github, "failed", previous=first)
        assert not [p for p in github.asked if "/jobs" in p or "/annotations" in p]
        assert again["red"]["tests"] == first["red"]["tests"]


# ---------------------------------------------------------------- the re-run, running

class TestTheReRunRunning:
    def _value(self, repo, github):
        return _read(repo, github, "rerunning", previous=_read(repo, github, "failed"))

    def test_the_row_stays_a_warning_saying_a_re_run_is_running(self, repo, github):
        v = self._value(repo, github)
        assert v["state"] == "verified"          # #1679's pass beside a live run: deployable
        (row,) = _rows(repo, v)
        assert row["level"] == "warning"
        assert row["what"].endswith("#1679 passed and #1680 failed, and #1680 is being re-run")
        assert ("#1679 attempt 1 passed; #1680 attempt 1 failed; #1680 attempt 2 is running"
                in row["cause"]), row["cause"]
        assert "A re-run is running: #1680 attempt 2 is running." in row["cause"]
        assert TEST in row["cause"]

    def test_its_action_is_nothing_while_the_re_run_runs(self, repo, github):
        (row,) = _rows(repo, self._value(repo, github), target="b" * 40)
        assert row["action"]["label"].startswith("Nothing: a re-run is running (#1680, "
                                                 "attempt 2)"), row["action"]
        assert "open" not in row["action"]

    def test_since_is_still_the_failed_attempts_completion(self, repo, github):
        (row,) = _rows(repo, self._value(repo, github))
        assert row["since"] == FAILED_AT

    def test_nothing_more_is_asked_about_the_failed_attempt(self, repo, github):
        first = _read(repo, github, "failed")
        github.asked.clear()
        _read(repo, github, "rerunning", previous=first)
        assert not [p for p in github.asked if "/jobs" in p or "/annotations" in p]


# ---------------------------------------------------------------- the re-run passed

class TestTheReRunPassed:
    def test_the_row_is_gone(self, repo, github):
        running = _read(repo, github, "rerunning", previous=_read(repo, github, "failed"))
        v = _read(repo, github, "rerun_passed", previous=running)
        assert v["state"] == "verified" and v["red"] is None
        assert _rows(repo, v) == []

    def test_through_the_readers_own_store(self, repo, github, monkeypatch):
        """Each read's previous red is the stored value's (the reader run as it runs)."""
        def store(state):
            github.state = state
            reader = dataclasses.replace(CV.READER, read=lambda: CV.read(
                commit=repo["tip"], get=github, root=repo["root"], store=repo["store"],
                fetch=lambda _root: ("absent", "origin holds no refs/notes/nmas-gate")))
            R.run_once(reader, clock=lambda: T0)
            return A.ci_source(pushed={"state": "absent", "doc": None, "why": "never"})["rows"]

        (failed,) = store("failed")
        assert failed["action"]["label"].startswith("Re-run the failed job")
        (running,) = store("rerunning")
        assert running["action"]["label"].startswith("Nothing: a re-run is running")
        assert store("rerun_passed") == []


# ---------------------------------------------------------------- reds with no pass beside

class TestARedWithNoPass:
    def test_a_lone_red_says_it_failed_in_its_own_words(self, repo, github):
        (row,) = _rows(repo, _read(repo, github, "alone"))
        assert row["level"] == "warning"
        assert row["what"] == f"The running commit {repo['tip'][:10]}: its CI run #1680 failed"
        assert "disagree" not in row["what"] and TEST in row["cause"]
        assert row["action"]["label"].startswith("Re-run the failed job")

    def test_a_red_re_run_is_fixed_forward_not_re_run_again(self, repo, github):
        """"A red may be rerun once" (the operator, 2026-11-03; ci_agreement.RERUNS_OFFERED).
        Attempt 2's jobs are answered by attempt 1's capture (no red attempt 2 was captured):
        the point is that a new failed attempt is asked about afresh."""
        first = _read(repo, github, "failed")
        github.asked.clear()
        v = _read(repo, github, "rerun_failed", previous=first)
        assert [p for p in github.asked if "/jobs" in p]
        (row,) = _rows(repo, v)
        assert row["level"] == "warning"
        assert row["action"]["label"].startswith("The developer fixes it forward: #1680 failed "
                                                 "again on its re-run (attempt 2)")

    def test_a_red_without_github_runs_drops_the_deploy_instruction(self, repo):
        """The local runner's red (no GitHub run asked): its sentence, without the deploy
        tool's instruction; no Update with no newer release; no start known."""
        mod = CV.deploy_script()
        sentence = (f"{mod.LOCAL_FAILED} for {repo['tip'][:10]}: the tests step failed. "
                    "Do not deploy this commit.")
        v = CV.read(commit=repo["tip"], verdict=lambda _root, _c: (mod.CI_REFUSED, sentence),
                    previous={})
        (row,) = _rows(repo, v)
        assert row["level"] == "warning" and "its CI run failed" in row["what"]
        assert "Do not deploy" not in row["cause"] and "the tests step failed" in row["cause"]
        assert "open" not in row["action"] and row["since"] is None
        (row,) = _rows(repo, v, target="b" * 40)
        assert row["action"]["open"] == "app_update"
