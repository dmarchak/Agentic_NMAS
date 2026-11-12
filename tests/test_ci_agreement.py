"""Workstream 0: the two CI runners on one commit, as a Needs attention source
(`modules/readers/ci_agreement.py`, `attention.ci_agreement_source`).

The operator, 2026-11-03: "A GitHub verdict that disagrees with the local one raises a Needs
attention row"; "A GitHub red that arrives after a deploy raises a Needs attention row naming the
step, with a rollback recommendation. A red may be rerun once: a green rerun clears it."

What is held:
- **the rows, from a stored value:** the running commit deployed on the local green and failed
  by GitHub since is one WARNING row (the operator, 2026-11-11: "severity by impact: it's no
  outage"; DANGER before) naming where it failed and the rollback's command, offering
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
from tests.test_notify import env  # noqa: F401 (the fixture: the notification stores and fakes)
from tests.test_cant_fix_email import zone  # noqa: F401 (the installation's zone, pinned)

#: C1522: the source reads reader stores; each test keeps them in its own folder.
pytestmark = pytest.mark.usefixtures("reader_stores_in_tmp")

A, B, C = "a" * 40, "b" * 40, "c" * 40


@pytest.fixture(scope="module")
def CA():
    """Imported inside a fixture, so on a commit without the module each test errors (red)."""
    from modules.readers import ci_agreement
    return ci_agreement


def _commit(sha, github, local, order, attempt=1, failed_at=None, words="w", gate="absent",
            gate_words=""):
    return {"sha": sha, "github": github, "local": local, "local_words": words, "order": order,
            "run": {"number": order, "attempt": attempt, "id": order * 10,
                    "url": f"https://github.com/owner/repo/actions/runs/{order * 10}"},
            "failed_at": failed_at, "gate": gate, "gate_words": gate_words}


def _value(commits, running=A, deployed=(A, B)):
    return {"slug": "owner/repo", "running": running, "deployed": list(deployed),
            "commits": commits}


def _cached(value, at="2026-11-03T12:50:00Z"):
    return {"state": "ok", "doc": {"last_good": {"value": value, "value_at": at},
                                   "stale_after_seconds": 2700}}


STEPS = [{"step": "Tests (R1, R4), confined to loopback, measured by tier", "jobs": ["test (a)"]}]


class TestTheRows:
    def test_a_github_red_after_a_local_green_deploy_is_one_warning_row(self, CA):
        v = _value([_commit(A, "FAILED", "passed", 9, failed_at=STEPS)])
        rows = attention.ci_agreement_source(cached=_cached(v), now=0)["rows"]
        assert [(r["kind"], r["level"]) for r in rows] == [("red-after-deploy", "warning")]
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
        assert r["action"]["label"].startswith("Stop new work. The rerun is spent; if it stays "
                                               "red, fix it forward or roll back")
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

    def test_a_github_red_after_a_gate_green_deploy_is_the_warning_row(self, CA):
        """The deploy bar (the operator, 2026-11-11): "If it goes red on a deployed sha: stop,
        report it at once, then fix forward or roll back"; a WARNING, "severity by impact:
        it's no outage"."""
        v = _value([_commit(A, "FAILED", "absent", 9, failed_at=STEPS, gate="passed")])
        rows = attention.ci_agreement_source(cached=_cached(v), now=0)["rows"]
        assert [(r["kind"], r["level"]) for r in rows] == [("red-after-deploy", "warning")]
        r = rows[0]
        assert "GitHub's CI failed aaaaaaaaaa, which this host runs (deployed on the gate's " \
               "green)" in r["what"]
        label = r["action"]["label"]
        assert label.startswith("Stop new work. ") and "reruns GitHub's run once" in label
        assert f"fix it forward or roll back: scripts/nmas-rollback {B[:10]} --push, then " \
               "Update" in label
        assert r["cause"] == "GitHub failed, the gate passed"

    def test_a_gate_green_github_agrees_with_raises_nothing(self, CA):
        assert CA.ours(_commit(A, "PASSED", "absent", 9, gate="passed")) == ("PASSED", "the gate")
        assert CA.judge(_value([_commit(A, "PASSED", "absent", 9, gate="passed")])) == []
        assert CA.judge(_value([_commit(A, "PENDING", "absent", 9, gate="passed")])) == []
        assert CA.judge(_value([_commit(A, "FAILED", "absent", 9, gate="none")])) == []

    def test_a_commit_the_host_does_not_run_with_a_gate_green_and_a_github_red_is_a_warning(
            self, CA):
        v = _value([_commit(C, "FAILED", "absent", 9, gate="passed", gate_words="12 step(s)")],
                   running=A)
        rows = attention.ci_agreement_source(cached=_cached(v), now=0)["rows"]
        assert [(r["kind"], r["level"]) for r in rows] == [("disagree", "warning")]
        assert "The gate and GitHub's CI disagree on cccccccccc" in rows[0]["what"]
        assert "the gate: 12 step(s)" in rows[0]["what"]

    def test_a_newer_commit_the_gate_and_github_both_pass_supersedes_it(self, CA):
        older = _commit(C, "FAILED", "absent", 9, gate="passed")
        assert [r["kind"] for r in CA.judge(_value([older], running=B))] == ["disagree"]
        v = _value([_commit(B, "PASSED", "absent", 10, gate="passed"), older], running=B)
        assert CA.judge(v) == []

    @pytest.mark.parametrize("gate", ["unreadable", "other-tree"])
    def test_a_gate_note_that_cannot_be_used_is_a_row(self, CA, gate):
        v = _value([_commit(C, "PASSED", "absent", 9, gate=gate, gate_words="names tree 0000")])
        rows = attention.ci_agreement_source(cached=_cached(v), now=0)["rows"]
        assert [(r["kind"], r["id"].split(":", 1)[1]) for r in rows] == [("unread", C)]
        assert "The gate's note on cccccccccc is not usable: names tree 0000" in rows[0]["what"]

    def test_notes_that_could_not_be_fetched_are_said_once_never_a_row_per_commit(self, CA):
        v = _value([_commit(A, "PASSED", "absent", 9, gate=CA.GATE_UNASKED),
                    _commit(C, "PASSED", "absent", 8, gate=CA.GATE_UNASKED)])
        v["gate_notes"] = {"state": "error", "words": "origin's notes could not be fetched (x)"}
        res = attention.ci_agreement_source(cached=_cached(v), now=0)
        assert res["rows"] == []
        assert "the gate's notes: origin's notes could not be fetched (x)" in json.dumps(res)

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
def world(tmp_path, monkeypatch):
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
    # The origin's URL is GitHub-shaped (for the slug); the gate's notes are fetched from a
    # real bare repository the test builds, as `fetch_gate_notes` fetches origin's.
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    from modules.readers import ci_verdict as CV

    def fetch(root):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        r = subprocess.run(["git", "-C", root, "fetch", "-q", str(origin),
                            "+refs/notes/nmas-gate:refs/notes/nmas-gate"],
                           capture_output=True, text=True, env=env, timeout=30)
        if r.returncode == 0:
            return "fetched", ""
        if "couldn't find remote ref" in r.stderr.lower():
            return "absent", "origin holds no refs/notes/nmas-gate"
        return "error", r.stderr.strip()
    # raising=False: on a script without it (the parent of the commit that adds it), the
    # stand-in is simply unused and the test's own body decides.
    monkeypatch.setattr(CV.deploy_script(), "fetch_gate_notes", fetch, raising=False)
    return {"repo": str(repo), "shas": shas, "origin": str(origin),
            "store": {"path": str(store), "owner": os.getuid()}}


def _gate(world, sha, tree=None):
    """The gate's verdict for *sha*, a note as scripts/nmas-gate step 9 writes it, pushed to
    the world's origin."""
    note = {"schema": 1, "sha": sha, "state": "passed", "scope": "full", "steps": [],
            "tree": tree or _git(world["repo"], "rev-parse", f"{sha}^{{tree}}"),
            "base": None, "host": "workstation", "at": "2026-11-11T20:00:00Z"}
    path = os.path.join(world["repo"], ".git", "note.json")
    with open(path, "w") as fh:
        json.dump(note, fh)
    _git(world["repo"], "notes", "--ref=refs/notes/nmas-gate", "add", "-f", "-F", path, sha)
    _git(world["repo"], "push", "-q", world["origin"], "refs/notes/nmas-gate")


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

    def test_each_commit_carries_the_gates_verdict_from_origins_notes(self, CA, world):
        s0, s1, s2 = world["shas"]
        _gate(world, s2)
        _gate(world, s1, tree="0" * 40)
        runs = [_run(s2, 12, "failure"), _run(s1, 11, "success"), _run(s0, 10, "success")]
        v = CA.read(world["repo"], get=_github(runs, []), store=world["store"], running=s2,
                    previous={})
        assert v["gate_notes"]["state"] == "fetched"
        got = [(c["sha"], c["github"], c["gate"]) for c in v["commits"]]
        assert got == [(s2, "FAILED", "passed"), (s1, "PASSED", "other-tree"),
                       (s0, "PASSED", "none")]
        rows = CA.judge(v)
        assert [(r["kind"], r["sha"], r.get("by") or r.get("unread_by")) for r in rows] == [
            ("red-after-deploy", s2, "the gate"), ("unread", s1, "the gate")]
        assert rows[0]["rollback_to"] == s1

    def test_no_notes_on_origin_raise_nothing_of_the_gate(self, CA, world):
        s2 = world["shas"][2]
        v = CA.read(world["repo"], get=_github([_run(s2, 12, "failure")], []),
                    store=world["store"], running=s2, previous={})
        assert v["gate_notes"]["state"] == "absent" and v["commits"][0]["gate"] == "absent"
        assert CA.judge(v) == []

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
        ("gate", "CI passed this release (the commit gate's recorded verdict)"),
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
        assert CV.source_of(mod, f"{mod.GATE_PASSED} for x: y") == "gate"
        assert CV.source_of(mod, "CI passed for x: run #3") == "github"


#: The release this host runs, as `update_op.last_deployed` names it after an Update.
DEPLOYED = {"to": A, "from": B, "requested_by": "pat@example.invalid", "route": "updater",
            "ended_at": "2026-11-11T20:00:00Z", "outcome": "updated"}


class TestTheNotice:
    """The operator's condition 1 (2026-11-11): the row has "its own notification kind "CI
    disagrees with the deployed release", on by default for the deployer". Sent once per commit
    and GitHub run, the first time the reader raises the row, through the delivery path every
    notice takes; to the teams the installation tells (each network's Who is told) until
    per-person preferences exist."""

    RED = staticmethod(lambda attempt=1, run_id=90: _value(
        [dict(_commit(A, "FAILED", "absent", 9, attempt=attempt, failed_at=STEPS,
                      gate="passed"), run={"number": 9, "attempt": attempt, "id": run_id,
                                           "url": "https://github.com/owner/repo/actions/runs/9"})]))

    def test_the_kind_is_declared_with_its_words(self, CA):
        from modules.notify import message
        assert message.EVENTS[CA.NOTIFY_EVENT] == "CI disagrees with the deployed release"
        assert CA.NOTIFY_ON_BY_DEFAULT is True

    def test_it_is_sent_once_and_not_again_on_the_next_read(self, CA):
        sent = []

        def deliver(event, teams):
            sent.append((event, teams))
            return {"ok": True, "sent": 1, "failed": 0}
        first = CA.notify_reds(self.RED(), {}, deliver=deliver, teams=["t1"], deployed=DEPLOYED,
                               now=0)
        assert len(sent) == 1 and sent[0][1] == ["t1"]
        assert first == {f"{A}:90": {"at": "1970-01-01T00:00:00Z", "sent": 1, "failed": 0,
                                     "teams": 1, "error": ""}}
        again = CA.notify_reds(self.RED(), {"notified": first}, deliver=deliver, teams=["t1"],
                               deployed=DEPLOYED, now=60)
        assert len(sent) == 1 and again == first
        CA.notify_reds(self.RED(attempt=2, run_id=91), {"notified": first}, deliver=deliver,
                       teams=["t1"], deployed=DEPLOYED, now=120)
        assert len(sent) == 2, "a rerun that fails again is a new notice"

    def test_no_red_after_deploy_sends_nothing(self, CA):
        sent = []
        CA.notify_reds(_value([_commit(C, "FAILED", "absent", 9, gate="passed")], running=A),
                       {}, deliver=lambda e, t: sent.append(e), teams=["t1"], deployed=DEPLOYED)
        assert sent == [], "a disagreement on a commit the host does not run is no notice"

    def test_its_words_name_the_sha_the_failed_job_the_deployer_and_the_history_link(self, CA,
                                                                                  zone):
        from modules.notify import message
        (r,) = CA.judge(self.RED())
        facts = message.check_event(CA.notice(r, DEPLOYED, now=0))
        assert facts["event"] == "ci_disagrees" and facts["incident"] == f"ci-{A[:12]}-90"
        text = message.text(facts, sent_at=0)
        assert text.startswith("Mercury: CI disagrees with the deployed release\n")
        assert f"GitHub's CI failed {A[:10]}, the release this host runs" in text
        assert "run #9, attempt 1, https://github.com/owner/repo/actions/runs/9" in text
        assert "failed at Tests (R1, R4), confined to loopback, measured by tier, in test (a)" \
            in text
        # Premise corrected (the operator, 2026-11-12, objective 2: a notice's body says "local
        # times"): the record's 2026-11-11T20:00:00Z in the installation's zone (pinned to
        # UTC+05:30), the zone named once at the end.
        assert ("Deployed by pat at 2026-11-12 01:30 (the Update button). "
                "The release keeps running: this is no outage.") in text
        assert text.rstrip().endswith("Times are in IST (UTC+05:30), the time zone of the host "
                                      "Mercury runs on.")
        assert f"scripts/nmas-rollback {B[:10]} --push, then Update" in text
        assert "Open in Mercury: /v2/history?kind=updates" in text

    def test_a_release_deployed_by_another_record_names_nobody(self, CA):
        (r,) = CA.judge(self.RED())
        event = CA.notice(r, dict(DEPLOYED, to=B), now=0)
        assert "Deployed by nobody recorded at an unrecorded time." in event["outcome"]

    def test_the_teams_told_are_each_networks_who_is_told_once(self, CA, monkeypatch):
        from modules import heal_notify
        teams = {"lab": "a1", "core": "", "edge": "a1", "dc": "b2"}
        monkeypatch.setattr(heal_notify, "read", lambda n: {"team": teams[n]})
        assert CA.told_teams(["lab", "core", "edge", "dc"]) == ["a1", "b2"]

    def test_a_delivery_failure_is_recorded_as_every_deliverys_is(self, CA, env):
        """Through the real delivery path: the relay refuses three times; the delivery log
        keeps each attempt with the kind, the notify source raises its row, and the notice is
        still not sent again on the next read."""
        from tests.test_notify import _relay, _team_with_email
        from modules.notify import delivery
        _relay(env)
        team, _dest = _team_with_email()
        env.smtp_fail[:] = [OSError("refused")] * 3
        first = CA.notify_reds(self.RED(), {}, teams=[team], deployed=DEPLOYED, now=0)
        assert first[f"{A}:90"] == dict(first[f"{A}:90"], sent=0, failed=1)
        rows = delivery.read_log()["rows"]
        assert len(rows) == 3 and {r["event"] for r in rows} == {"ci_disagrees"}
        assert rows[0]["outcome"] == "failed" and rows[0]["final"] is True
        assert [r["kind"] for r in attention.notify_source()["rows"]] == ["failed"]
        CA.notify_reds(self.RED(), {"notified": first}, teams=[team], deployed=DEPLOYED, now=60)
        assert len(delivery.read_log()["rows"]) == 3

    def test_a_delivered_notice_carries_its_words_to_the_mailbox(self, CA, env):
        from tests.test_notify import _mail, _relay, _team_with_email
        _relay(env)
        team, _dest = _team_with_email()
        got = CA.notify_reds(self.RED(), {}, teams=[team], deployed=DEPLOYED, now=0)
        assert got[f"{A}:90"]["sent"] == 1
        (msg,) = [_mail(raw) for s in env.smtp for raw in s.sent]
        assert "CI disagrees with the deployed release" in msg["Subject"]
        body = msg.get_body(("plain",)).get_content()
        # The deployer by display name (board E2a), never their address.
        assert A[:10] in body and "Deployed by pat at" in body and "test (a)" in body
        assert "pat@example.invalid" not in body
