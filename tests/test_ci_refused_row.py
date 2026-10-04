"""C418: a pushed commit CI refused is the failure, never an update on offer.

The operator, 2026-10-04: Needs attention said "Update available — c2440a6 → 74a7013 ... preview
the commits and CI's verdict, then confirm" for a commit CI had failed, and the Update button
refuses such a commit. Now the row leads with the failure ("CI failed on the newest commit,
74a7013 — run #373: <the failed step, in its jobs>"), its action is the developer's fix forward,
and it links the run.

Where a run failed comes from GitHub's jobs listing for the run, captured for two real failures
(tests/fixtures/github/: run #373, the promtool step in all three jobs; run #333, the tests step
of the one job of that time), the account replaced by a placeholder. The run's number and link
come from `nmas-deploy`'s own verdict sentences, produced here by the real `ci_verdict()` through
a fake GitHub, never typed (C421: the Update page's "run #" pattern missed the number in the
commonest sentence, a run of the commit's own).
"""

import json
import os
import subprocess

import pytest

from modules import attention
from modules.readers import app_pushed as P
from modules.readers import ci_verdict as CV

HERE = os.path.dirname(os.path.abspath(__file__))
SLUG = "account/Agentic_NMAS"
RUN_ID = "37165035014"
URL = f"https://github.com/{SLUG}/actions/runs/{RUN_ID}"
PROMTOOL = "promtool for the PromQL tests (unpacked, not installed)"


def _jobs(n):
    with open(os.path.join(HERE, "fixtures", "github", f"jobs_run{n}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _git(cwd, *args):
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True,
                         env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                                  GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com"))
    return out.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """Two commits and a GitHub-shaped origin URL (nothing is fetched)."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
    shas = []
    for i in range(2):
        (tmp_path / "f").write_text(str(i))
        _git(tmp_path, "add", "f")
        _git(tmp_path, "commit", "-q", "-m", f"c{i}")
        shas.append(_git(tmp_path, "rev-parse", "HEAD"))
    return {"root": str(tmp_path), "base": shas[0], "tip": shas[1]}


def _run(conclusion, status="completed", n=373, url=URL, at="2026-10-04T00:28:07Z"):
    return {"path": ".github/workflows/ci.yml", "status": status, "conclusion": conclusion,
            "run_number": n, "run_attempt": 1, "html_url": url, "created_at": at,
            "updated_at": at}


def _sentence(repo, runs_for):
    """`nmas-deploy`'s real verdict, through a GitHub answering *runs_for[sha]*."""
    mod = CV.deploy_script()

    def get(path):
        sha = next((s for s in runs_for if f"head_sha={s}" in path), None)
        return 200, {"workflow_runs": runs_for.get(sha, [])}, ""

    code, sentence = mod.ci_verdict(repo["root"], repo["tip"], get=get)
    return CV.state_of(mod, code), sentence


# ------------------------------------------------------------ the run, from the verdict

class TestTheRunIsReadFromEveryFormOfTheVerdict:
    def test_a_failed_run_of_the_commits_own(self, repo):
        state, sentence = _sentence(repo, {repo["tip"]: [_run("failure")]})
        assert state == "failed"
        assert CV.run_of(sentence) == {"number": "373", "url": URL, "slug": SLUG, "id": RUN_ID}

    def test_the_run_judged_not_another_run_listed_after_it(self, repo):
        state, sentence = _sentence(repo, {repo["tip"]: [
            _run("failure", n=374, at="2026-10-04T01:00:00Z"),
            _run("cancelled", n=372, at="2026-10-04T00:00:00Z")]})
        assert state == "failed" and "#372" in sentence
        assert CV.run_of(sentence)["number"] == "374"

    def test_a_run_still_going(self, repo):
        state, sentence = _sentence(repo, {repo["tip"]: [_run(None, status="in_progress")]})
        assert state == "pending" and CV.run_of(sentence)["number"] == "373"

    def test_a_cancelled_commit_has_a_link_and_no_number(self, repo):
        state, sentence = _sentence(repo, {repo["tip"]: [_run("cancelled")]})
        assert state == "cancelled"
        assert CV.run_of(sentence) == {"number": None, "url": URL, "slug": SLUG, "id": RUN_ID}

    def test_an_ancestors_failed_run_has_a_number_and_no_link(self, repo):
        state, sentence = _sentence(repo, {repo["base"]: [_run("failure", n=370)]})
        assert state == "failed"
        assert CV.run_of(sentence) == {"number": "370", "url": None, "slug": None, "id": None}

    def test_an_ancestors_run_still_going(self, repo):
        state, sentence = _sentence(repo, {repo["base"]: [_run(None, status="queued", n=370)]})
        assert state == "pending" and CV.run_of(sentence)["number"] == "370"

    def test_the_update_page_names_the_run_of_the_commits_own(self, repo):
        """C421: "run #(\\d+)" found nothing in "run for 74a7013b5c, #373, concluded"."""
        from modules import update_op

        _state, sentence = _sentence(repo, {repo["tip"]: [_run("failure")]})
        words = update_op.person_ci({"tip": repo["tip"], "state": "failed", "sentence": sentence})
        assert words.startswith("CI failed for this release (run #373):"), words


# ------------------------------------------------------------ where it failed

class TestWhereARunFailed:
    def test_one_step_in_three_jobs_is_said_once(self):
        asked = []
        got = CV.failed_steps(CV.run_of(f"... #373, concluded failure: {URL}. Do not"),
                              get=lambda p: (asked.append(p), (200, _jobs("373"), ""))[1])
        assert asked == [f"/repos/{SLUG}/actions/runs/{RUN_ID}/jobs?per_page=50"]
        assert got == {"steps": [{"step": PROMTOOL,
                                  "jobs": ["test (a)", "test (b)", "test (browser)"]}]}
        assert CV.failed_words({"failed_at": got["steps"]}) == (
            f"{PROMTOOL}, in test (a), test (b), test (browser)")

    def test_the_tests_step_of_the_one_job(self):
        got = CV.failed_steps({"slug": SLUG, "id": "37093186912"},
                              get=lambda p: (200, _jobs("333"), ""))
        assert got == {"steps": [{"step": "Tests (R1, R4), confined to loopback, coverage reported",
                                  "jobs": ["test"]}]}

    def test_github_not_answering_is_said_with_its_reason(self):
        got = CV.failed_steps({"slug": SLUG, "id": RUN_ID}, get=lambda p: (0, None, "rate-limited"))
        assert got == {"error": f"GitHub's jobs for run {RUN_ID} could not be read (rate-limited)"}

    def test_no_run_of_its_own_asks_nothing(self):
        got = CV.failed_steps({"slug": None, "id": None},
                              get=lambda p: pytest.fail("asked GitHub with no run to ask about"))
        assert "names no run" in got["error"]


class TestTheReaderAsksOncePerFailedTip:
    def _behind(self, repo):
        return {"running": repo["base"], "tip": repo["tip"], "state": "behind", "behind": 1,
                "branch": "main"}

    def test_a_failed_verdict_records_where_and_is_not_asked_again(self, repo):
        sentence = f"FAILED: CI's latest conclusive run for x, #373, concluded failure: {URL}. Do not"
        asked = []
        jobs = lambda p: (asked.append(p), (200, _jobs("373"), ""))[1]   # noqa: E731
        first = P.enrich(repo["root"], self._behind(repo), {}, verdict=lambda r, t: (CV.deploy_script().CI_REFUSED, sentence),
                         jobs=jobs)
        assert first["ci"]["state"] == "failed" and len(asked) == 1
        assert first["ci"]["failed_at"][0]["step"] == PROMTOOL
        again = P.enrich(repo["root"], self._behind(repo), first,
                         verdict=lambda r, t: pytest.fail("a final verdict was asked again"),
                         jobs=jobs)
        assert again["ci"] == first["ci"] and len(asked) == 1

    def test_a_verdict_that_is_not_a_failure_asks_for_no_jobs(self, repo):
        mod = CV.deploy_script()
        for code in (mod.OK, mod.CI_PENDING, mod.CI_CANCELLED):
            out = P.enrich(repo["root"], self._behind(repo), {},
                           verdict=lambda r, t: (code, f"run #373 {URL}"),
                           jobs=lambda p: pytest.fail("asked for the jobs of a run that did not fail"))
            assert "failed_at" not in out["ci"]


# ------------------------------------------------------------ the row

def _source(ci, monkeypatch, state="behind"):
    from routes import health

    monkeypatch.setattr(health, "_COMMIT", "a" * 40)
    value = {"running": "a" * 40, "tip": "b" * 40, "state": state, "behind": 2,
             "branch": "main", "behind_since": "2026-10-04T00:30:00Z", "ci": ci}
    return attention.pushed_source(cached={"state": "ok", "doc": {"last_good": {
        "value": value, "value_at": "2026-10-04T00:40:00Z"}, "stale_after_seconds": 750}})


def _failed(**extra):
    return {"tip": "b" * 40, "state": "failed", "asked_at": "2026-10-04T00:39:00Z",
            "sentence": f"FAILED: CI's latest conclusive run for bbbbbbbbbb, #373, concluded "
                        f"failure: {URL}. Do not deploy this commit.",
            "failed_at": [{"step": PROMTOOL, "jobs": ["test (a)", "test (b)", "test (browser)"]}],
            **extra}


class TestTheRowLeadsWithTheFailure:
    def test_the_headline_is_the_failure_and_the_action_the_developers(self, monkeypatch):
        (row,) = _source(_failed(), monkeypatch)["rows"]
        assert row["kind"] == "ci_failed" and row["level"] == "warning"
        assert row["what"] == (f"CI failed on the newest commit, bbbbbbb — run #373: {PROMTOOL}, "
                               "in test (a), test (b), test (browser)")
        assert row["action"] == {"known": True,
                                 "label": "The developer fixes forward; nothing to update until "
                                          "CI passes a newer commit", "run_url": URL, "run": "373"}
        assert "concluded failure" in row["cause"]

    def test_it_never_offers_the_update(self, monkeypatch):
        for ci in (_failed(), _failed(state="cancelled")):
            (row,) = _source(ci, monkeypatch)["rows"]
            said = f"{row['what']} {row['action']['label']}".lower()
            assert "update available" not in said and "confirm" not in said, said
            assert "open" not in row["action"]

    def test_a_cancelled_commit_says_no_verdict(self, monkeypatch):
        ci = _failed(state="cancelled", failed_at=None,
                     sentence=f"CANCELLED: every CI run for bbbbbbbbbb was cancelled: {URL}.")
        (row,) = _source(ci, monkeypatch)["rows"]
        assert row["what"] == "CI was cancelled for the newest commit, bbbbbbb: no verdict"
        assert row["action"]["run_url"] == URL and row["action"]["run"] == ""

    def test_a_verdict_stored_before_where_was_asked_still_leads_with_the_failure(self, monkeypatch):
        """The host's stored verdict for 74a7013 predates `failed_at`."""
        ci = _failed()
        del ci["failed_at"]
        (row,) = _source(ci, monkeypatch)["rows"]
        assert row["what"] == "CI failed on the newest commit, bbbbbbb — run #373"

    def test_where_could_not_be_read_is_said(self, monkeypatch):
        (row,) = _source(_failed(failed_at=[], failed_at_error="GitHub's jobs for run 1 could "
                                 "not be read (rate-limited)"), monkeypatch)["rows"]
        assert row["what"] == "CI failed on the newest commit, bbbbbbb — run #373"
        assert "Where it failed could not be read: GitHub's jobs" in row["cause"]

    def test_another_commits_failure_is_not_this_tips(self, monkeypatch):
        assert _source(_failed(tip="c" * 40), monkeypatch)["rows"] == []

    def test_a_running_commit_off_the_remote_stays_that_row(self, monkeypatch):
        (row,) = _source(_failed(), monkeypatch, state="not_on_remote")["rows"]
        assert row["kind"] == "release"

    def test_the_quiet_update_indicator_stays_quiet(self):
        v = {"running": "a" * 40, "tip": "b" * 40, "state": "behind", "behind": 2, "ci": _failed()}
        assert attention.update_available(v, last={}) is None


class TestTheRowIsDrawn:
    def test_the_run_is_linked_and_no_update_button_is_drawn(self, monkeypatch):
        import app as A

        (row,) = _source(_failed(), monkeypatch)["rows"]
        page = {"ok": True, "headline": "", "rows": [row], "unreadable": [],
                "badge": attention.badge_of([row], []), "sources": []}
        monkeypatch.setattr("modules.attention.needs_attention", lambda sources=None: page)
        monkeypatch.setattr("modules.nsot.receipts.read",
                            lambda list_name, device="", limit=50: {"state": "absent", "rows": []})
        html = A.app.test_client().get("/v2/").get_data(as_text=True)
        assert (f'<a class="btn btn-small btn-outline" href="{URL}" target="_blank" '
                f'rel="noopener noreferrer">Open run #373 on GitHub</a>') in html
        assert "CI failed on the newest commit, bbbbbbb" in html
        assert 'data-next-acts="update_page"' not in html

    def test_only_a_github_address_is_drawn_as_the_run(self, monkeypatch):
        import app as A

        row = attention.row(source="pushed", kind="ci_failed", key="k", level="warning",
                            what="W", cause="C", action={"label": "The developer fixes forward",
                                                         "run_url": "javascript:alert(1)"})
        page = {"ok": True, "headline": "", "rows": [row], "unreadable": [],
                "badge": attention.badge_of([row], []), "sources": []}
        monkeypatch.setattr("modules.attention.needs_attention", lambda sources=None: page)
        monkeypatch.setattr("modules.nsot.receipts.read",
                            lambda list_name, device="", limit=50: {"state": "absent", "rows": []})
        html = A.app.test_client().get("/v2/").get_data(as_text=True)
        assert "javascript:alert" not in html and "on GitHub" not in html
