"""Workstream 0: the two CI runners on one commit, as a Needs attention source
(`modules/readers/ci_agreement.py`, `attention.ci_agreement_source`).

The operator, 2026-11-03: "A GitHub verdict that disagrees with the local one raises a Needs
attention row"; "A GitHub red that arrives after a deploy raises a Needs attention row naming the
step, with a rollback recommendation. A red may be rerun once: a green rerun clears it."

What is held:
- **the rows, from a stored value:** the running commit deployed on the local green and failed
  by GitHub since is one DANGER row naming where it failed and the rollback's command, offering
  the one rerun until its attempt is spent; a commit the host does not run with one green and
  one red is a WARNING row, either way round; it clears when the two agree (a green rerun) or a
  NEWER commit's two verdicts agree (superseded); agreement, a pending GitHub run and no local
  record raise nothing; an untrusted or unreadable local record is a row; one row per commit;
- **the read:** GitHub asked once for main's push runs, each commit judged by `nmas-deploy`'s
  own `verdict_of_runs` and `local_verdict` (a real repository and a real store), a red's
  failed steps asked once and carried while its run is the same;
- **the wiring:** kinds and clears declared, the source's key announced by the reader, the
  reader declared;
- **the Update page says which runner passed a release.**

GitHub's answers here are built in the test, in the shape `tests/fixtures/github/` captures
(the runs listing's `head_sha`, `path`, `status`, `conclusion`, `run_number`, `run_attempt`).
"""
import json
import os
import subprocess

import pytest

from modules import attention

#: C1522: the source reads reader stores; each test keeps them in its own folder.
pytestmark = pytest.mark.usefixtures("reader_stores_in_tmp")

A, B, C = "a" * 40, "b" * 40, "c" * 40


@pytest.fixture(scope="module")
def CA():
    """Imported inside a fixture, so on a commit without the module each test errors (red)."""
    from modules.readers import ci_agreement
    return ci_agreement


def _commit(sha, github, local, order, attempt=1, failed_at=None, words="w"):
    return {"sha": sha, "github": github, "local": local, "local_words": words, "order": order,
            "run": {"number": order, "attempt": attempt, "id": order * 10,
                    "url": f"https://github.com/owner/repo/actions/runs/{order * 10}"},
            "failed_at": failed_at}


def _value(commits, running=A, deployed=(A, B)):
    return {"slug": "owner/repo", "running": running, "deployed": list(deployed),
            "commits": commits}


def _cached(value, at="2026-11-03T12:50:00Z"):
    return {"state": "ok", "doc": {"last_good": {"value": value, "value_at": at},
                                   "stale_after_seconds": 2700}}


STEPS = [{"step": "Tests (R1, R4), confined to loopback, measured by tier", "jobs": ["test (a)"]}]


class TestTheRows:
    def test_a_github_red_after_a_local_green_deploy_is_one_danger_row(self, CA):
        v = _value([_commit(A, "FAILED", "passed", 9, failed_at=STEPS)])
        rows = attention.ci_agreement_source(cached=_cached(v), now=0)["rows"]
        assert [(r["kind"], r["level"]) for r in rows] == [("red-after-deploy", "danger")]
        r = rows[0]
        assert "GitHub's CI failed aaaaaaaaaa, which this host runs" in r["what"]
        assert "failed at Tests (R1, R4), confined to loopback, measured by tier, in test (a)" \
            in r["what"]
        assert "reruns GitHub's run once" in r["action"]["label"]
        assert f"scripts/nmas-rollback {B[:10]} --push, then Update" in r["action"]["label"]
        assert r["action"]["run_url"].endswith("/runs/90")

    def test_the_rerun_is_offered_once(self, CA):
        v = _value([_commit(A, "FAILED", "passed", 9, attempt=2, failed_at=STEPS)])
        r = attention.ci_agreement_source(cached=_cached(v), now=0)["rows"][0]
        assert r["action"]["label"].startswith("The rerun is spent; if it stays red, roll back")
        assert CA.judge(v)[0]["rerun_left"] is False

    def test_a_green_rerun_clears_it(self, CA):
        assert CA.judge(_value([_commit(A, "PASSED", "passed", 9, attempt=2)])) == []

    @pytest.mark.parametrize("github, local", [("FAILED", "passed"), ("PASSED", "failed")])
    def test_a_commit_the_host_does_not_run_that_they_disagree_on_is_a_warning(self, CA,
                                                                               github, local):
        v = _value([_commit(C, github, local, 9)], running=A)
        rows = attention.ci_agreement_source(cached=_cached(v), now=0)["rows"]
        assert [(r["kind"], r["level"], r["id"].split(":", 1)[1]) for r in rows] == [("disagree", "warning", C)]
        assert "The two CI runners disagree on cccccccccc" in rows[0]["what"]

    def test_a_newer_commit_both_pass_supersedes_it(self, CA):
        v = _value([_commit(B, "PASSED", "passed", 10), _commit(C, "FAILED", "passed", 9)],
                   running=B)
        assert CA.judge(v) == []
        v = _value([_commit(B, "PASSED", "passed", 8), _commit(C, "FAILED", "passed", 9)],
                   running=B)
        assert [r["kind"] for r in CA.judge(v)] == ["disagree"], "an OLDER agreement does not"

    def test_the_running_commit_is_never_superseded(self, CA):
        v = _value([_commit(B, "PASSED", "passed", 10), _commit(A, "FAILED", "passed", 9)])
        assert [r["kind"] for r in CA.judge(v)] == ["red-after-deploy"]

    @pytest.mark.parametrize("github, local", [("PASSED", "passed"), ("FAILED", "failed"),
                                               ("PENDING", "passed"), ("PASSED", "none"),
                                               ("PASSED", "absent"), ("FAILED", "running"),
                                               ("CANCELLED", "failed")])
    def test_agreement_or_no_verdict_raises_nothing(self, CA, github, local):
        assert CA.judge(_value([_commit(A, github, local, 9)])) == []

    @pytest.mark.parametrize("local", ["untrusted", "unreadable", "other-tree"])
    def test_a_local_record_that_cannot_be_used_is_a_row(self, CA, local):
        v = _value([_commit(C, "PASSED", local, 9, words="owned by uid 1000, not 0")])
        rows = attention.ci_agreement_source(cached=_cached(v), now=0)["rows"]
        assert [(r["kind"], r["id"].split(":", 1)[1]) for r in rows] == [("unread", C)]
        assert "owned by uid 1000, not 0" in rows[0]["what"]

    def test_one_row_per_commit(self, CA):
        """Three commits, none of whose two verdicts agree: three rows, one each."""
        v = _value([_commit(A, "FAILED", "passed", 9), _commit(C, "PASSED", "failed", 11),
                    _commit(B, "FAILED", "passed", 7)])
        keys = [r["id"].split(":", 1)[1] for r in attention.ci_agreement_source(cached=_cached(v),
                                                                now=0)["rows"]]
        assert len(keys) == len(set(keys)) == 3 and set(keys) == {A, B, C}

    def test_a_source_never_read_says_so(self, CA):
        res = attention.ci_agreement_source(cached={"state": "missing", "why": "no store",
                                                    "doc": {}}, now=0)
        assert res["state"] == "unreadable" and "not read yet: no store" in json.dumps(res)


def _git(repo, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=env, timeout=30).stdout.strip()


@pytest.fixture
def world(tmp_path):
    repo = tmp_path / "checkout"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    shas = []
    for i in range(3):
        (repo / "app.py").write_text(f"v = {i}\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", f"c{i}")
        shas.append(_git(repo, "rev-parse", "HEAD"))
    _git(repo, "remote", "add", "origin", "github-nmas:owner/repo.git")
    store = tmp_path / "store"
    (store / "verdicts").mkdir(parents=True)
    os.chmod(store, 0o755)
    os.chmod(store / "verdicts", 0o755)
    return {"repo": str(repo), "shas": shas,
            "store": {"path": str(store), "owner": os.getuid()}}


def _local(world, sha, state):
    rec = {"schema": 1, "kind": "push", "sha": sha, "state": state,
           "tree": _git(world["repo"], "rev-parse", f"{sha}^{{tree}}"), "jobs": [], "failed": []}
    path = os.path.join(world["store"]["path"], "verdicts", f"{sha}.json")
    with open(path, "w") as fh:
        json.dump(rec, fh)
    os.chmod(path, 0o644)


def _github(runs, asked):
    def get(path):
        asked.append(path)
        if "/jobs" in path:
            return 200, {"jobs": [{"name": "test (a)", "conclusion": "failure",
                                   "steps": [{"name": "Tests", "conclusion": "failure"}]}]}, ""
        return 200, {"workflow_runs": runs}, ""
    return get


def _run(sha, number, conclusion, attempt=1):
    return {"head_sha": sha, "path": ".github/workflows/ci.yml", "status": "completed",
            "conclusion": conclusion, "run_number": number, "run_attempt": attempt,
            "id": number * 100, "html_url": f"https://github.com/owner/repo/actions/runs/{number}"}


class TestTheRead:
    def test_each_commit_is_judged_by_the_deploy_scripts_own_verdicts(self, CA, world):
        s0, s1, s2 = world["shas"]
        _local(world, s2, "passed")
        _local(world, s1, "failed")
        asked = []
        runs = [_run(s2, 12, "failure"), _run(s1, 11, "success"), _run(s0, 10, "success")]
        v = CA.read(world["repo"], get=_github(runs, asked), store=world["store"],
                    running=s2, previous={})
        got = [(c["sha"], c["github"], c["local"]) for c in v["commits"]]
        assert got == [(s2, "FAILED", "passed"), (s1, "PASSED", "failed"), (s0, "PASSED", "none")]
        assert v["commits"][0]["failed_at"] == [{"step": "Tests", "jobs": ["test (a)"]}]
        assert asked[0] == "/repos/owner/repo/actions/runs?branch=main&event=push&per_page=50"
        assert len(asked) == 2, "one listing, and one jobs request for the one red"
        rows = CA.judge(v)
        assert [(r["kind"], r["sha"]) for r in rows] == [("red-after-deploy", s2),
                                                         ("disagree", s1)]

    def test_a_reds_steps_are_asked_once_and_carried(self, CA, world):
        s2 = world["shas"][2]
        _local(world, s2, "passed")
        runs = [_run(s2, 12, "failure")]
        first = CA.read(world["repo"], get=_github(runs, []), store=world["store"], running=s2,
                        previous={})
        asked = []
        CA.read(world["repo"], get=_github(runs, asked), store=world["store"], running=s2,
                previous=first)
        assert len(asked) == 1, asked
        asked = []
        rerun = [_run(s2, 12, "failure", attempt=2) | {"id": 9999}]
        CA.read(world["repo"], get=_github(rerun, asked), store=world["store"], running=s2,
                previous=first)
        assert len(asked) == 2, "a new run's red is asked about afresh"

    def test_github_unreadable_fails_the_read_so_the_last_value_stands(self, CA, world):
        with pytest.raises(RuntimeError, match="could not be read"):
            CA.read(world["repo"], get=lambda p: (0, None, "URLError: timed out"),
                    store=world["store"], running=world["shas"][2], previous={})


class TestTheWiring:
    def test_kinds_clears_keys_and_the_reader_are_declared(self, CA):
        from modules import invalidation, reader_job
        for kind in ("red-after-deploy", "disagree", "unread"):
            assert ("ci_agreement", kind) in attention.ROW_KINDS
            assert ("ci_agreement", kind) in attention.CLEARS
        assert attention.SOURCE_KEYS["ci_agreement_source"] == ("ci_agreement",)
        assert attention.ci_agreement_source in attention.SOURCES
        assert "ci_agreement" in invalidation.VOCABULARY
        assert "modules.readers.ci_agreement" in reader_job.DECLARED_MODULES
        assert CA.READER.invalidates == ("ci_agreement",)


class TestTheUpdatePageSaysWhichRunner:
    @pytest.mark.parametrize("source, words", [
        ("local", "CI passed this release (the local CI runner on this host)"),
        ("github", "CI passed this release (GitHub's CI)"),
        ("override", "CI passed this release (the operator's override of the two runners' "
                     "disagreement)")])
    def test_a_verified_release_names_its_runner(self, source, words):
        from modules import update_op
        assert update_op.person_ci({"tip": A, "state": "verified", "source": source},
                                   A) == words

    def test_the_readers_store_the_source(self):
        from modules.readers import ci_verdict as CV
        mod = CV.deploy_script()
        assert CV.source_of(mod, f"{mod.LOCAL_PASSED} for x: y") == "local"
        assert CV.source_of(mod, "CI passed for x: run #3") == "github"
