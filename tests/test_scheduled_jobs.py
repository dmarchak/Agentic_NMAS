"""C2347: a scheduled quality job that fails, or has not succeeded within its period, is a Needs
attention row (the operator's rule, 2026-11-03).

Measured that morning: the mutation workflow's scheduled runs had all failed (#67 and #68 the
newest), and the coverage nightly's #32 to #34 (10-29 to 10-31) too, and nothing said so.

The fixtures are GitHub's own answers, captured 2026-11-03 through `nmas-deploy`'s `github_get`
(tests/fixtures/github/): each workflow's last 10 scheduled runs on main, and run #68's jobs, the
fields the reader reads kept and the account replaced by a placeholder. The 10-31 state is the
coverage capture with its three newer runs removed, so the failure the operator found unsaid is
the case the row is shown on.
"""

import calendar
import json
import os
import subprocess
import time

import pytest

from modules import attention
from modules.readers import scheduled_jobs as SJ

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SLUG = "account/Agentic_NMAS"


def _fixture(name):
    with open(os.path.join(HERE, "fixtures", "github", name), encoding="utf-8") as fh:
        return json.load(fh)


def _epoch(stamp):
    return calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))


MUTATION = _fixture("mutation-nightly_scheduled_runs.json")
COVERAGE = _fixture("coverage-nightly_scheduled_runs.json")
JOBS_68 = _fixture("jobs_mutation_run68.json")


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path):
    """A checkout with this repository's two scheduled workflows and its CI workflow, and a
    GitHub-shaped origin (nothing is fetched)."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    for name in ("mutation-nightly.yml", "coverage-nightly.yml", "ci.yml"):
        with open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8") as fh:
            (wf / name).write_text(fh.read())
    return str(tmp_path)


def _github(runs=None, jobs=None, refuse=()):
    """A fake `github_get` answering from the captures; every path it was asked is kept."""
    runs = {"mutation-nightly.yml": MUTATION, "coverage-nightly.yml": COVERAGE,
            **(runs or {})}
    asked = []

    def get(path):
        asked.append(path)
        for name, body in runs.items():
            if f"/actions/workflows/{name}/runs?" in path:
                if name in refuse:
                    return 403, None, "rate-limited"
                return 200, body, ""
        if path.endswith("/jobs?per_page=50"):
            return 200, jobs or JOBS_68, ""
        return 404, None, "HTTP 404"
    get.asked = asked
    return get


def _by_file(value):
    return {w["file"]: w for w in value["workflows"]}


class TestThePopulation:
    def test_it_is_every_workflow_with_a_schedule_and_never_ci(self):
        """The repository's own workflows, read where this process runs: the two with a cron,
        never ci.yml (it runs on every push, and its verdict is the ci row)."""
        found = {w["file"]: w for w in SJ.scheduled_workflows(ROOT)}
        assert {"mutation-nightly.yml", "coverage-nightly.yml"} <= set(found)
        assert "ci.yml" not in found
        assert found["coverage-nightly.yml"]["period_seconds"] == 86400
        assert found["mutation-nightly.yml"]["period_seconds"] == 7 * 86400

    def test_a_workflow_with_no_schedule_is_not_one(self, tmp_path):
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "push.yml").write_text("on:\n  push:\njobs: {}\n")
        (wf / "weekly.yml").write_text("name: W\non:\n  schedule:\n    - cron: '0 1 * * 2'\n"
                                       "jobs:\n  a:\n    timeout-minutes: 30\n")
        assert [w["file"] for w in SJ.scheduled_workflows(str(tmp_path))] == ["weekly.yml"]

    def test_a_run_s_bound_is_its_jobs_timeouts_summed(self):
        """The mutation workflow's jobs bound at 2 and 230 minutes, and steps inside them, so
        its run's bound is the jobs' 232 minutes; a job with none takes GitHub's 360."""
        found = {w["file"]: w for w in SJ.scheduled_workflows(ROOT)}
        assert found["mutation-nightly.yml"]["run_bound_seconds"] >= 232 * 60
        assert SJ.run_bound_of({"jobs": {"a": {}, "b": {"timeout-minutes": 10}}}) == 370 * 60

    @pytest.mark.parametrize("cron,period", [
        ("0 14 * * 0", 7 * 86400), ("47 3 * * *", 86400), ("0 0 1 * *", 31 * 86400),
        ("15 */6 * * *", 6 * 3600), ("5 * * * *", 3600), ("not a cron", None), ("", None)])
    def test_a_cron_s_period(self, cron, period):
        assert SJ.period_of(cron) == period


class TestTheStartDelay:
    def test_the_bound_is_2_5_times_the_worst_lateness_measured(self):
        """GitHub starts a scheduled run late: measured from the captures against each cron, by
        a path independent of the reader (the cron's time of day, the run's created_at)."""
        worst = 0
        for body, (hour, minute) in ((COVERAGE, (3, 47)), (MUTATION, (14, 0))):
            for r in body["workflow_runs"]:
                created = _epoch(r["created_at"])
                day = created - created % 86400
                due = day + hour * 3600 + minute * 60
                if r["created_at"] >= "2026-10-25" and created >= due:
                    worst = max(worst, created - due)
        assert worst >= 7 * 3600, f"the captures' worst lateness is {worst} s"
        assert SJ.START_DELAY_SECONDS >= 2.5 * worst * 0.99
        assert SJ.START_DELAY_SECONDS <= 3 * worst


class TestTheRead:
    def test_each_workflow_s_newest_run_and_last_success(self, repo):
        get = _github()
        got = _by_file(SJ.read(repo, get=get))
        mutation, coverage = got["mutation-nightly.yml"], got["coverage-nightly.yml"]
        assert mutation["newest"]["run_number"] == 68
        assert mutation["newest"]["conclusion"] == "failure"
        assert mutation["last_success"] is None
        assert coverage["newest"]["run_number"] == 37
        assert coverage["last_success"]["run_number"] == 37
        assert all("event=schedule&branch=main" in p for p in get.asked if "/workflows/" in p)

    def test_a_failed_newest_run_names_where_it_failed(self, repo):
        """Run #68's jobs, captured: the mutate job failed at "The report"."""
        got = _by_file(SJ.read(repo, get=_github()))
        assert got["mutation-nightly.yml"]["failed_at"] == [{"step": "The report",
                                                             "jobs": ["mutate"]}]
        assert got["coverage-nightly.yml"]["failed_at"] is None

    def test_one_workflow_unreadable_keeps_the_other(self, repo):
        got = _by_file(SJ.read(repo, get=_github(refuse=("mutation-nightly.yml",))))
        assert "rate-limited" in got["mutation-nightly.yml"]["error"]
        assert got["coverage-nightly.yml"]["newest"]["run_number"] == 37

    def test_none_readable_fails_the_read_so_the_last_good_stands(self, repo):
        with pytest.raises(RuntimeError, match="mutation-nightly.yml.*rate-limited"):
            SJ.read(repo, get=_github(refuse=("mutation-nightly.yml", "coverage-nightly.yml")))


def _on_10_31():
    """The coverage capture as GitHub listed it on 10-31: #34, #33 and #32 the newest, failed."""
    runs = [r for r in COVERAGE["workflow_runs"] if r["run_number"] <= 34]
    return dict(COVERAGE, workflow_runs=runs)


class TestTheJudgment:
    def test_the_mutation_run_s_failures_are_failed(self, repo):
        w = _by_file(SJ.read(repo, get=_github()))["mutation-nightly.yml"]
        verdict = SJ.judge(w, now=_epoch("2026-11-03T13:00:00Z"))
        assert verdict["state"] == "failed"
        assert "#68" in verdict["words"] and "failure" in verdict["words"]
        assert "no success in its last 4 scheduled runs" in verdict["words"]

    def test_the_coverage_nightly_on_10_31_is_failed(self, repo):
        """The state the operator found said nowhere: three nightly failures in a row."""
        get = _github(runs={"coverage-nightly.yml": _on_10_31()})
        w = _by_file(SJ.read(repo, get=get))["coverage-nightly.yml"]
        verdict = SJ.judge(w, now=_epoch("2026-10-31T12:00:00Z"))
        assert verdict["state"] == "failed"
        assert "#34" in verdict["words"] and "#31" in verdict["words"]

    def test_the_coverage_nightly_today_is_ok(self, repo):
        w = _by_file(SJ.read(repo, get=_github()))["coverage-nightly.yml"]
        assert SJ.judge(w, now=_epoch("2026-11-03T13:00:00Z"))["state"] == "ok"

    def test_a_success_older_than_its_bound_is_overdue(self, repo):
        """A schedule that stopped running (GitHub stops scheduling an idle repository's
        workflows): the last success ages past its period, start delay and run bound."""
        w = _by_file(SJ.read(repo, get=_github()))["coverage-nightly.yml"]
        done = _epoch(w["last_success"]["updated_at"])
        limit = SJ.overdue_after(w)
        assert limit == 86400 + SJ.START_DELAY_SECONDS + w["run_bound_seconds"]
        assert SJ.judge(w, now=done + limit - 60)["state"] == "ok"
        assert SJ.judge(w, now=done + limit + 60)["state"] == "overdue"

    def test_a_run_still_going_is_not_judged(self, repo):
        """The newest COMPLETED run is judged: one in progress is not a verdict."""
        going = dict(COVERAGE["workflow_runs"][0], id=1, run_number=38, status="in_progress",
                     conclusion=None)
        body = dict(COVERAGE, workflow_runs=[going] + COVERAGE["workflow_runs"])
        w = _by_file(SJ.read(repo, get=_github(runs={"coverage-nightly.yml": body})))
        assert w["coverage-nightly.yml"]["newest"]["run_number"] == 37


def _cached(value, at="2026-11-03T12:50:00Z"):
    return {"state": "ok", "doc": {"last_good": {"value": value, "value_at": at},
                                   "stale_after_seconds": 3600}}


class TestTheRow:
    def test_the_mutation_run_is_one_warning_row_with_its_run(self, repo):
        value = SJ.read(repo, get=_github())
        res = attention.scheduled_jobs_source(cached=_cached(value),
                                              now=_epoch("2026-11-03T13:00:00Z"))
        rows = res["rows"]
        assert [(r["source"], r["kind"], r["id"]) for r in rows] == [
            ("scheduled_jobs", "failed", "scheduled_jobs:mutation-nightly.yml")]
        r = rows[0]
        assert r["level"] == "warning"
        assert "#68" in r["what"] and "The report, in mutate" in r["what"]
        assert r["action"]["run"] == "68"
        assert r["action"]["run_url"].endswith("/actions/runs/41337732668")
        assert "coverage-nightly.yml: ok" in res["checked"]

    def test_every_kind_says_how_it_clears(self):
        for kind in ("failed", "overdue", "unread"):
            assert ("scheduled_jobs", kind) in attention.CLEARS
            assert ("scheduled_jobs", kind) in attention.ROW_KINDS

    def test_an_unreadable_workflow_is_a_row_of_its_own(self, repo):
        value = SJ.read(repo, get=_github(refuse=("coverage-nightly.yml",)))
        res = attention.scheduled_jobs_source(cached=_cached(value),
                                              now=_epoch("2026-11-03T13:00:00Z"))
        kinds = {r["id"]: r["kind"] for r in res["rows"]}
        assert kinds == {"scheduled_jobs:mutation-nightly.yml": "failed",
                         "scheduled_jobs:coverage-nightly.yml": "unread"}

    def test_a_reader_that_never_stored_a_value_is_the_source_unreadable(self):
        res = attention.scheduled_jobs_source(
            cached={"state": "ok", "doc": {"last_attempt": {"error": "HTTP 403"}}})
        assert res["state"] == "unreadable"
        assert "HTTP 403" in res["rows"][0]["cause"]

    def test_the_reader_is_in_the_population_job_health_watches(self):
        from modules import reader_job
        assert "modules.readers.scheduled_jobs" in reader_job.DECLARED_MODULES
        assert attention.SOURCE_KEYS["scheduled_jobs_source"] == ("scheduled_jobs",)
