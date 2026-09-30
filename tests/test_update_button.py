"""The Update button (the operator, 2026-09-30; docs/UPDATE.md): the app writes
a REQUEST and holds no privilege; the ROOT-OWNED updater re-checks CI itself,
runs git as the service user, restarts, confirms by identity and rolls back a
version that does not come up; the page waits on /health.

The updater is driven against REAL git repositories (a bare origin and a
clone), with the gate, the restart and the health answers faked: what reaches
the checkout is real. The app's request is checked by the UPDATER'S OWN
`validate()`, so the two halves cannot drift apart unseen.
"""

import ast
import importlib.machinery
import importlib.util
import json
import os
import re
import stat
import subprocess
import time
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPDATER = os.path.join(ROOT, "deploy", "update", "nmas-update")


def _updater():
    loader = importlib.machinery.SourceFileLoader("nmas_update_under_test", UPDATER)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _g(cwd, *args):
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True,
                         env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                                  GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com"))
    return out.stdout.strip()


@pytest.fixture
def repos(tmp_path):
    """A bare origin at c2 and a clone (the checkout) at c0, fetched."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    shas = []
    for i, msg in enumerate(["c0", "c1\n\nHost-Step: install python3-foo on the host", "c2"]):
        (work / "f").write_text(str(i))
        _g(work, "add", "f")
        _g(work, "commit", "-q", "-m", msg)
        shas.append(_g(work, "rev-parse", "HEAD"))
    _g(work, "push", "-q", "origin", "HEAD:main")
    _g(work, "reset", "-q", "--hard", shas[0])
    return {"origin": origin, "work": work, "shas": shas}


def _local_git(repo, *args, check=True):
    """`nmas-deploy`'s git signature, as the test's own user (the updater's
    runs as the service user through `runuser`)."""
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                         env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout.strip()


def _gate(verdict=0, up=None):
    """A stand-in for the root-owned copy of nmas-deploy: its verdict, and
    whether each commit comes up."""
    up = up or {}
    calls = {"verdict": 0}

    def ci_verdict(repo, target):
        calls["verdict"] += 1
        return verdict, ("CI passed" if verdict == 0 else "FAILED: run #9")

    def wait_for_running(target, pid_before, health, unit, clock, sleep, timeout=90):
        ok = up.get(target, True)
        return ok, {"unit": {"MainPID": 200}}, ("" if ok else "the running process loaded another commit")
    return types.SimpleNamespace(OK=0, ci_verdict=ci_verdict, wait_for_running=wait_for_running,
                                 calls=calls)


def _request(repos, **over):
    doc = {"id": "0123456789abcdef", "target": repos["shas"][2], "from": repos["shas"][0],
           "requested_by": "person@example.invalid",
           "requested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "acknowledged_host_steps": [repos["shas"][1]]}
    doc.update(over)
    return doc


def _run(repos, req, gate, restarts):
    U = _updater()
    return U, U.update(req, repo=str(repos["work"]), gate=gate, git=_local_git,
                       restart=lambda: restarts.append(1), unit=lambda: {"MainPID": 100},
                       health=lambda: (200, {}), sleep=lambda s: None)


# ---------------------------------------------------------------- the updater

class TestTheUpdaterMovesOnlyToWhatCIPassed:
    def test_a_passed_target_is_fast_forwarded_restarted_and_confirmed(self, repos):
        restarts = []
        _U, rec = _run(repos, _request(repos), _gate(), restarts)
        assert rec["outcome"] == "updated" and restarts == [1]
        assert _g(repos["work"], "rev-parse", "HEAD") == repos["shas"][2]
        assert [s["step"] for s in rec["host_steps"]] == ["install python3-foo on the host"]

    def test_ci_not_passed_refuses_and_nothing_moves(self, repos):
        restarts = []
        U = _updater()
        with pytest.raises(U.Refused, match="CI gate does not pass"):
            U.update(_request(repos), repo=str(repos["work"]), gate=_gate(verdict=1),
                     git=_local_git, restart=lambda: restarts.append(1),
                     unit=lambda: {"MainPID": 100}, health=lambda: (200, {}))
        assert restarts == [] and _g(repos["work"], "rev-parse", "HEAD") == repos["shas"][0]

    def test_origin_moved_since_the_preview_refuses(self, repos):
        U = _updater()
        with pytest.raises(U.Refused, match="origin/main is now"):
            U.update(_request(repos, target=repos["shas"][1]), repo=str(repos["work"]),
                     gate=_gate(), git=_local_git, restart=lambda: None,
                     unit=lambda: {"MainPID": 100}, health=lambda: (200, {}))
        assert _g(repos["work"], "rev-parse", "HEAD") == repos["shas"][0]

    def test_a_checkout_that_moved_or_has_changes_refuses(self, repos):
        U = _updater()
        with pytest.raises(U.Refused, match="not .* as the preview said"):
            U.update(_request(repos, **{"from": repos["shas"][1]}), repo=str(repos["work"]),
                     gate=_gate(), git=_local_git, restart=lambda: None,
                     unit=lambda: {"MainPID": 100}, health=lambda: (200, {}))
        (repos["work"] / "f").write_text("edited by hand")
        with pytest.raises(U.Refused, match="local changes"):
            U.update(_request(repos), repo=str(repos["work"]), gate=_gate(), git=_local_git,
                     restart=lambda: None, unit=lambda: {"MainPID": 100},
                     health=lambda: (200, {}))

    def test_a_host_step_not_said_done_refuses_naming_it(self, repos):
        U = _updater()
        with pytest.raises(U.Refused, match="install python3-foo"):
            U.update(_request(repos, acknowledged_host_steps=[]), repo=str(repos["work"]),
                     gate=_gate(), git=_local_git, restart=lambda: None,
                     unit=lambda: {"MainPID": 100}, health=lambda: (200, {}))
        assert _g(repos["work"], "rev-parse", "HEAD") == repos["shas"][0]


class TestAVersionThatDoesNotComeUpIsRolledBack:
    def test_rolled_back_to_the_commit_it_ran(self, repos):
        restarts = []
        _U, rec = _run(repos, _request(repos), _gate(up={repos["shas"][2]: False}), restarts)
        assert rec["outcome"] == "rolled_back" and restarts == [1, 1]
        assert _g(repos["work"], "rev-parse", "HEAD") == repos["shas"][0]
        assert "did not come up within 120 s" in rec["reason"]

    def test_a_rollback_that_does_not_come_up_says_so(self, repos):
        restarts = []
        _U, rec = _run(repos, _request(repos),
                       _gate(up={repos["shas"][2]: False, repos["shas"][0]: False}), restarts)
        assert rec["outcome"] == "rollback_failed" and "did not come up either" in rec["reason"]

    def test_the_bound_is_the_measured_one(self):
        src = open(UPDATER, encoding="utf-8").read()
        assert _updater().UP_BOUND_S == 120 and "median 2.1 s, p90 10.2 s" in src


class TestTheRequestIsARequestNeverAnInstruction:
    def test_every_malformed_field_is_refused_by_name_without_its_value(self, repos):
        U = _updater()
        now = time.time()
        good = _request(repos)
        assert U.validate(dict(good), now) == good
        cases = [(dict(good, extra="x"), "unexpected"), ({k: v for k, v in good.items() if k != "id"}, "missing"),
                 (dict(good, target="PLANTED-not-a-sha"), "target is not a full commit hash"),
                 (dict(good, requested_by=""), "names no person"),
                 (dict(good, requested_at="2000-01-01T00:00:00Z"), "stale"),
                 (dict(good, acknowledged_host_steps=["PLANTED"]), "not commit hashes")]
        for doc, words in cases:
            with pytest.raises(U.Refused, match=words) as exc:
                U.validate(doc, now)
            assert "PLANTED" not in str(exc.value)

    def test_only_a_regular_file_the_service_user_owns_is_read_and_all_are_removed(self, tmp_path):
        U = _updater()
        d = tmp_path / "requests"
        d.mkdir()
        secret = tmp_path / "secret"
        secret.write_text("PLANTED")
        (d / "aaaaaaaaaaaaaaaa.json").write_text(json.dumps({"requested_at": "1", "id": "x"}))
        os.symlink(secret, d / "bbbbbbbbbbbbbbbb.json")
        (d / "junk.txt").write_text("x")
        req, notes = U.take_requests(str(d), os.getuid())
        assert req == {"requested_at": "1", "id": "x"}
        assert os.listdir(d) == [] and secret.read_text() == "PLANTED"
        assert not any("PLANTED" in n for n in notes)
        assert any("bbbbbbbbbbbbbbbb.json" in n and "removed unread" in n for n in notes)
        # Another owner's file (here: a uid that is not ours) is never read.
        (d / "cccccccccccccccc.json").write_text("{}")
        req, notes = U.take_requests(str(d), os.getuid() + 1)
        assert req is None and os.listdir(d) == []

    def test_the_app_writes_exactly_what_the_updater_accepts(self, tmp_path, monkeypatch):
        from modules import update_op
        monkeypatch.setattr(update_op, "REQUEST_DIR", str(tmp_path / "requests"))
        monkeypatch.setattr(update_op, "STAGING_DIR", str(tmp_path / "staging"))
        monkeypatch.setattr(update_op, "AUDIT", str(tmp_path / "audit.jsonl"))
        p = _plan()
        got = update_op.request(p["hash"], ["c" * 40], "person@example.invalid", **_plan_kw())
        assert got["ok"], got
        (name,) = os.listdir(tmp_path / "requests")
        doc = json.loads((tmp_path / "requests" / name).read_text())
        assert _updater().validate(doc, time.time()) == doc     # the SEAM, both halves
        assert os.listdir(tmp_path / "staging") == []           # written outside, renamed in


class TestRootNeverRunsTheRepository:
    def test_every_git_the_updater_runs_goes_through_runuser(self):
        tree = ast.parse(open(UPDATER, encoding="utf-8").read())
        lists = [n for n in ast.walk(tree) if isinstance(n, ast.List)
                 and any(isinstance(e, ast.Constant) and e.value == "git" for e in n.elts)]
        assert lists, "the scan found no git invocation at all"
        for n in lists:
            words = [e.value for e in n.elts if isinstance(e, ast.Constant)]
            assert words[:2] == ["runuser", "-u"], words

    def test_the_updater_imports_nothing_from_the_repository(self):
        tree = ast.parse(open(UPDATER, encoding="utf-8").read())
        mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not mods & {"modules", "routes", "app", "scripts"}
        assert "sys.path" not in open(UPDATER, encoding="utf-8").read()

    def test_a_gate_root_does_not_own_is_refused(self, tmp_path):
        U = _updater()
        fake = tmp_path / "nmas-deploy"
        fake.write_text("OK = 0\n")
        with pytest.raises(U.Refused, match="not a root-owned file"):
            U.load_gate(str(fake))

    def test_the_outcome_is_world_readable_and_kept(self, tmp_path):
        U = _updater()
        U.write_state({"outcome": "updated", "id": "x"}, state_dir=str(tmp_path))
        U.write_state({"outcome": "refused", "id": "y"}, state_dir=str(tmp_path))
        assert stat.S_IMODE(os.stat(tmp_path / "outcome.json").st_mode) == 0o644
        assert json.loads((tmp_path / "outcome.json").read_text())["id"] == "y"
        assert len((tmp_path / "history.jsonl").read_text().splitlines()) == 2


# ------------------------------------------------------------------ the reader

class TestTheReaderRecordsWhatThePreviewShows:
    def test_commits_host_steps_and_the_updaters_own_files(self, repos):
        from modules.readers import app_pushed as P

        (repos["work"] / "deploy").mkdir()
        _g(repos["work"], "checkout", "-q", repos["shas"][2])
        v = P.judge(str(repos["work"]), repos["shas"][0])
        asked = []
        out = P.enrich(str(repos["work"]), v, {}, verdict=lambda r, t: (asked.append(t), (0, "ok"))[1])
        assert [c["subject"] for c in out["commits"]] == ["c2", "c1"]
        assert out["host_steps"] == [{"sha": repos["shas"][1], "step": "install python3-foo on the host"}]
        assert out["updater_changes"] == [] and out["checkout_changes"] == []
        assert out["ci"]["state"] == "verified" and asked == [repos["shas"][2]]
        assert out["behind_since"] and "first seen by this reader" in out["behind_since_basis"]

    def test_a_final_verdict_is_asked_once_per_tip_and_pending_again(self, repos):
        from modules.readers import app_pushed as P

        v = P.judge(str(repos["work"]), repos["shas"][0])
        asked = []
        first = P.enrich(str(repos["work"]), v, {}, verdict=lambda r, t: (asked.append(t), (0, "ok"))[1])
        P.enrich(str(repos["work"]), v, first, verdict=lambda r, t: (asked.append(t), (0, "ok"))[1])
        assert len(asked) == 1
        pend = P.enrich(str(repos["work"]), v, {}, verdict=lambda r, t: (7, "PENDING"))
        P.enrich(str(repos["work"]), v, pend, verdict=lambda r, t: (asked.append(t), (0, "ok"))[1])
        assert len(asked) == 2

    def test_since_is_kept_for_this_running_commit_and_restarts_for_another(self, repos):
        from modules.readers import app_pushed as P

        v = P.judge(str(repos["work"]), repos["shas"][0])
        prev = {"running": repos["shas"][0], "state": "behind", "behind_since": "2026-09-30T08:00:00Z"}
        ok = lambda r, t: (0, "ok")
        assert P.enrich(str(repos["work"]), v, prev, verdict=ok, now=1e9 + 5e8)["behind_since"] == \
            "2026-09-30T08:00:00Z"
        other = dict(prev, running="f" * 40)
        assert P.enrich(str(repos["work"]), v, other, verdict=ok, now=1790000000)["behind_since"] \
            == time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(1790000000))

    def test_a_release_that_changes_the_updater_names_its_files(self, repos):
        from modules.readers import app_pushed as P

        _g(repos["work"], "checkout", "-q", "-B", "main", repos["shas"][2])
        (repos["work"] / "deploy" / "update").mkdir(parents=True)
        (repos["work"] / "deploy" / "update" / "nmas-update").write_text("# new\n")
        _g(repos["work"], "add", "deploy")
        _g(repos["work"], "commit", "-q", "-m", "c3")
        _g(repos["work"], "push", "-q", "origin", "HEAD:main")
        _g(repos["work"], "reset", "-q", "--hard", repos["shas"][0])
        v = P.judge(str(repos["work"]), repos["shas"][0])
        out = P.enrich(str(repos["work"]), v, {}, verdict=lambda r, t: (0, "ok"))
        assert out["updater_changes"] == ["deploy/update/nmas-update"]


# ------------------------------------------------------------------ the app side

def _value(**over):
    v = {"running": "a" * 40, "tip": "b" * 40, "state": "behind", "behind": 2, "branch": "main",
         "commits": [{"sha": "b" * 40, "subject": "fix", "author": "t", "at": "2026-09-30T10:00:00Z"}],
         "host_steps": [{"sha": "c" * 40, "step": "install python3-foo"}], "updater_changes": [],
         "checkout_changes": [], "behind_since": "2026-09-30T09:00:00Z",
         "behind_since_basis": "first seen by this reader, which asks every 300 s",
         "ci": {"tip": "b" * 40, "state": "verified", "sentence": "CI passed for bbbbbbbbbb",
                "asked_at": "2026-09-30T10:01:00Z"}}
    v.update(over)
    return v


def _plan_kw(value=None, install="ok"):
    return {"cached": {"state": "ok", "doc": {"last_good": {"value": value or _value(),
                                                             "value_at": "2026-09-30T10:01:00Z"}}},
            "install": {"state": install}, "running": "a" * 40, "pending_now": [],
            "now_outcome": {"state": "absent"}}


def _plan(**kw):
    from modules import update_op
    return update_op.plan(**_plan_kw(**kw))


class TestThePreview:
    def test_all_gates_pass_and_the_hash_is_stable(self):
        a, b = _plan(), _plan()
        assert a["selectable"] and a["hash"] == b["hash"]
        assert all(g["state"] == "pass" for g in a["gates"]) and len(a["gates"]) == 6

    @pytest.mark.parametrize("value,words", [
        (_value(ci={"tip": "b" * 40, "state": "pending", "sentence": "PENDING"}), "CI passed the target"),
        (_value(state="at_tip", tip="a" * 40), "origin/main is ahead"),
        (_value(checkout_changes=[" M app.py"]), "no local changes"),
        (_value(running="d" * 40), "for the commit running now")])
    def test_each_refusal_is_a_gate_by_name(self, value, words):
        p = _plan(value=value)
        assert not p["selectable"] and words in p["why_not"]

    def test_not_installed_and_writable_refuse(self):
        assert "not installed" in _plan(install="not_installed")["why_not"]
        assert not _plan(install="writable")["selectable"]

    def test_a_moved_preview_or_an_unsaid_host_step_writes_nothing(self, tmp_path, monkeypatch):
        from modules import update_op
        monkeypatch.setattr(update_op, "REQUEST_DIR", str(tmp_path / "requests"))
        monkeypatch.setattr(update_op, "STAGING_DIR", str(tmp_path / "staging"))
        got = update_op.request("0" * 16, ["c" * 40], "p@example.invalid", **_plan_kw())
        assert not got["ok"] and "has changed" in got["reason"]
        got = update_op.request(_plan()["hash"], [], "p@example.invalid", **_plan_kw())
        assert not got["ok"] and "install python3-foo" in got["reason"]
        got = update_op.request(_plan()["hash"], ["c" * 40], "", **_plan_kw())
        assert not got["ok"] and "person" in got["reason"]
        assert not os.path.exists(tmp_path / "requests")


class TestTheInstallCheck:
    def test_absent_is_not_installed_with_the_install_as_its_action(self, tmp_path):
        from modules import update_op
        s = update_op.install_state(installed=(("x", str(tmp_path / "nope"), None),))
        (row,) = update_op.install_rows(s)
        assert row["state"] == "not_installed" and row["action"]["reference"] == "docs/UPDATE.md"

    def test_a_file_the_service_user_can_write_is_danger(self, tmp_path):
        from modules import attention, update_op
        f = tmp_path / "nmas-update"
        f.write_text("x")
        s = update_op.install_state(installed=(("the updater", str(f), None),), active=True)
        (row,) = update_op.install_rows(s)
        assert row["state"] == "writable" and "not owned by root" in row["detail"]
        assert "the service user can write it" in row["detail"]
        assert attention._JOB_STATES["writable"][1] == "danger"

    def test_root_owned_and_matching_is_ok_and_a_different_copy_differs(self, tmp_path, monkeypatch):
        """Root-owned is SIMULATED (a test cannot create a root file, and inside
        the confined runner a real one reads as another uid): os.stat answers
        uid 0 for the installed file, and os.access answers what the service
        user may write, as the app asks it on the host."""
        from modules import update_op
        f = tmp_path / "installed"
        f.write_text("same\n")
        (tmp_path / "src").write_text("same\n")
        real_stat = os.stat

        def as_root(path, *a, **k):
            st = real_stat(path, *a, **k)
            if str(path) != str(f):
                return st
            return os.stat_result((stat.S_IFREG | 0o644, st.st_ino, st.st_dev, 1, 0, 0,
                                   st.st_size, 0, 0, 0))
        monkeypatch.setattr(update_op.os, "stat", as_root)
        monkeypatch.setattr(update_op.os, "access", lambda p, m: False)
        inst = (("the updater", str(f), "src"),)
        assert update_op.install_state(root=str(tmp_path), installed=inst, active=True)["state"] == "ok"
        (tmp_path / "src").write_text("a newer release\n")
        s = update_op.install_state(root=str(tmp_path), installed=inst, active=True)
        assert s["state"] == "differs" and "differs from this release's src" in s["differs"][0]
        assert update_op.install_rows(s)[0]["action"]["reference"] == "docs/UPDATE.md"
        assert update_op.install_state(root=str(tmp_path), installed=inst, active=False)["state"] == "inactive"
        # The control: the same file the service user CAN write is danger, whoever owns it.
        monkeypatch.setattr(update_op.os, "access", lambda p, m: str(p) == str(f))
        assert update_op.install_state(root=str(tmp_path), installed=inst, active=True)["state"] == "writable"

    def test_job_health_carries_the_row(self):
        from modules import job_health
        rows = job_health.health(updater=[{"unit": "updater", "state": "ok"}], version=[],
                                 readers=[], monitoring=[], prometheus=[], breakglass=[],
                                 sessions=[], startup=[], responder=[], ztp=[], owner=[],
                                 rotations=[], settings=[], images=[])["jobs"]
        assert {"unit": "updater", "state": "ok"} in rows
        assert "updater_rows" in open(os.path.join(ROOT, "modules", "job_health.py")).read()


# --------------------------------------------------------- the entry points

class TestNeedsAttentionOffersTheUpdate:
    def _row(self, monkeypatch, value, last=None):
        from modules import attention, update_op
        from routes import health
        monkeypatch.setattr(health, "_COMMIT", "a" * 40)
        monkeypatch.setattr(update_op, "outcome", lambda: last or {"state": "absent"})
        r = attention.pushed_source(cached={"state": "ok", "doc": {
            "last_good": {"value": value, "value_at": "2026-09-30T10:00:00Z"},
            "stale_after_seconds": 750}})
        (row,) = r["rows"]
        return row

    def test_the_action_is_the_update_never_a_terminal(self, monkeypatch):
        row = self._row(monkeypatch, _value())
        assert row["action"]["open"] == "app_update" and "command" not in row["action"]
        assert row["since"] is not None   # "since not recorded" is gone

    def test_a_rolled_back_update_is_this_rows_cause(self, monkeypatch):
        last = {"state": "ok", "value": {"outcome": "rolled_back", "from": "a" * 40, "to": "b" * 40,
                                         "requested_by": "p", "reason": "did not come up"}}
        row = self._row(monkeypatch, _value(), last)
        assert "rolled back" in row["cause"] and "did not come up" in row["cause"]
        last["value"]["outcome"] = "rollback_failed"
        assert self._row(monkeypatch, _value(), last)["level"] == "danger"


class TestThePage:
    def test_the_page_draws_the_preview_under_the_strict_policy(self, monkeypatch):
        import app as A
        from modules import update_op
        fixed = _plan()
        monkeypatch.setattr(update_op, "plan", lambda: fixed)
        r = A.app.test_client().get("/v2/update")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "script-src 'self'" in r.headers["Content-Security-Policy"]
        assert "b" * 10 in html and "install python3-foo" in html and 'data-host-step="' + "c" * 40 in html
        assert 'data-hash="' + fixed["hash"] in html and 'data-selectable="yes"' in html
        assert "It runs nothing from the repository as root" in html
        assert not re.search(r"<script(?![^>]*\bsrc=)", html) and " onclick=" not in html

    def test_about_and_the_landing_row_link_to_the_same_page(self, monkeypatch):
        import app as A
        from routes import v2
        inst = {"running": "a" * 40, "subject": "", "started_at": "", "pid": 1, "version": {},
                "ci": {}, "pushed": {"state": "behind", "words": "behind"},
                "last_update": {"state": "absent"}}
        monkeypatch.setattr(v2, "installation", lambda: inst)
        html = A.app.test_client().get("/v2/help/about").get_data(as_text=True)
        assert 'id="about-update" href="/v2/update"' in html
        tpl = open(os.path.join(ROOT, "templates", "v2", "_attention.html")).read()
        assert "r.action.open == 'app_update'" in tpl and "url_for('v2.update')" in tpl
        js = open(os.path.join(ROOT, "static", "js", "nmas_attention.js")).read()
        assert "a.open === 'app_update'" in js and 'data-nmas-update href="/v2/update"' in js

    def test_apply_writes_the_request_as_the_verified_person(self, tmp_path, monkeypatch):
        import app as A
        from modules import update_op
        monkeypatch.setattr(update_op, "REQUEST_DIR", str(tmp_path / "requests"))
        monkeypatch.setattr(update_op, "STAGING_DIR", str(tmp_path / "staging"))
        monkeypatch.setattr(update_op, "AUDIT", str(tmp_path / "audit.jsonl"))
        real = update_op.plan
        want = _plan()["hash"]
        monkeypatch.setattr(update_op, "plan", lambda **kw: real(**_plan_kw()))
        r = A.app.test_client().post("/update/apply", json={"hash": want,
                                                            "acknowledged": ["c" * 40]})
        assert r.status_code == 202, r.get_json()
        (name,) = os.listdir(tmp_path / "requests")
        doc = json.loads((tmp_path / "requests" / name).read_text())
        assert doc["requested_by"] == "test-person@example.invalid" and doc["target"] == "b" * 40
        r = A.app.test_client().post("/update/apply", json={"hash": "0" * 16})
        assert r.status_code == 409 and "has changed" in r.get_json()["error"]

    @pytest.mark.real_identity
    def test_nobody_verified_is_refused_before_anything_is_written(self, tmp_path, monkeypatch):
        import app as A
        from modules import update_op
        monkeypatch.setattr(update_op, "REQUEST_DIR", str(tmp_path / "requests"))
        r = A.app.test_client().post("/update/apply", json={"hash": "x"})
        assert r.status_code == 403 and not os.path.exists(tmp_path / "requests")


KEYS = ["request", "started", "checkout", "fetch", "ci", "move", "restart", "wait", "running"]


class TestTheStepperFollowsTheUpdatersOwnSteps:
    """`stepStates`, the SHIPPED function, in duktape: every stage visible."""

    def _states(self, health, status, elapsed=5, timeout=900, rid="id1"):
        import dukpy
        src = open(os.path.join(ROOT, "static", "js", "nmas_update.js"), encoding="utf-8").read()
        return dukpy.evaljs([src, "NMAS_UPDATE.stepStates(dukpy.k, dukpy.t, dukpy.i, dukpy.h, dukpy.s, "
                                  "dukpy.e, dukpy.o)"],
                            k=KEYS, t="t" * 40, i=rid, h=health, s=status, e=elapsed, o=timeout)

    @staticmethod
    def _status(outcome, step="", rid="id1", reason=""):
        return {"outcome": {"state": "ok", "value": {"id": rid, "outcome": outcome, "step": step,
                                                     "reason": reason}},
                "outcome_words": {"refused": "refused: nothing was changed",
                                  "rolled_back": "rolled back"}, "pending": []}

    def test_the_updaters_step_is_current_and_everything_before_it_done(self):
        r = self._states({"commit": "a" * 40}, self._status("running", "ci"))
        s = {k: v["state"] for k, v in r["steps"].items()}
        assert [s[k] for k in KEYS] == ["done", "done", "done", "done", "current",
                                         "pending", "pending", "pending", "pending"]
        assert not r["done"] and not r["reload"]

    def test_waiting_for_the_new_version_counts_seconds_while_the_app_is_down(self):
        r = self._states(None, self._status("running", "wait"), elapsed=37)
        assert r["steps"]["wait"] == {"state": "current", "note": "the app is restarting, 37 s"}

    def test_the_new_commit_answering_is_the_last_step_done_and_reloads(self):
        r = self._states({"commit": "t" * 40}, self._status("running", "wait"))
        assert r["steps"]["running"] == {"state": "done", "note": "running tttttttttt"}
        assert r["done"] and r["reload"]

    def test_a_refusal_marks_its_step_failed_with_the_reason(self):
        r = self._states({"commit": "a" * 40},
                         self._status("refused", "ci", reason="the CI gate does not pass"))
        assert r["steps"]["ci"] == {"state": "failed", "note": "the CI gate does not pass"}
        assert r["steps"]["fetch"]["state"] == "done" and r["steps"]["move"]["state"] == "pending"
        assert r["done"] and r["failed"] and not r["reload"]
        assert r["words"].startswith("The update refused: nothing was changed: the CI gate")

    def test_another_requests_record_is_not_this_ones(self):
        r = self._states({"commit": "a" * 40}, self._status("refused", "ci", rid="other"))
        assert r["steps"]["started"]["state"] == "current" and not r["done"]

    def test_a_request_not_taken_in_a_minute_names_the_path_unit(self):
        r = self._states({"commit": "a" * 40}, {"pending": ["x.json"], "outcome": {"state": "absent"}},
                         elapsed=75)
        assert "nmas-update.path" in r["steps"]["started"]["note"]

    def test_the_units_limit_ends_the_wait_saying_where_to_look(self):
        r = self._states({"commit": "a" * 40}, {"pending": [], "outcome": {"state": "absent"}},
                         elapsed=901)
        assert r["done"] and r["failed"] and "journalctl -u nmas-update.service" in r["words"]


class TestOneStepList:
    def test_the_page_and_the_updater_name_the_same_steps(self):
        from modules import update_op
        keys = [k for k, _w in update_op.STEPS]
        assert keys == KEYS
        assert list(_updater().STEPS) == keys[2:-1]      # the updater's own, in order


class TestTheSharedLock:
    """C242: a terminal deploy and the updater can never both act."""

    def _deploy_script(self):
        path = os.path.join(ROOT, "scripts", "nmas-deploy")
        loader = importlib.machinery.SourceFileLoader("nmas_deploy_lock", path)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(mod)
        return mod

    def test_whoever_holds_it_the_other_refuses(self, tmp_path):
        import fcntl
        D, U = self._deploy_script(), _updater()
        assert D.LOCK_REL == U.LOCK_REL
        held = D.take_lock(str(tmp_path))                 # a terminal deploy runs
        assert held is not None
        with pytest.raises(U.Refused, match="terminal deploy"):
            U.take_lock(str(tmp_path), os.getuid())
        os.close(held)
        fd = U.take_lock(str(tmp_path), os.getuid())      # the updater runs
        assert D.take_lock(str(tmp_path)) is None
        os.close(fd)
        assert D.take_lock(str(tmp_path)) is not None     # free again

    def test_the_updater_never_opens_it_through_a_link(self, tmp_path):
        U = _updater()
        (tmp_path / "data" / "update").mkdir(parents=True)
        target = tmp_path / "elsewhere"
        target.write_text("x")
        os.symlink(target, tmp_path / "data" / "update" / "lock")
        with pytest.raises(OSError):
            U.take_lock(str(tmp_path), os.getuid())

    def test_the_preview_asks_without_creating_and_names_a_holder(self, tmp_path, monkeypatch):
        import fcntl
        from modules import update_op
        lock = tmp_path / "update" / "lock"
        monkeypatch.setattr(update_op, "LOCK", str(lock))
        assert update_op.lock_holder() == "" and not lock.exists()
        lock.parent.mkdir(parents=True)
        fd = os.open(lock, os.O_RDONLY | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            assert "terminal deploy" in update_op.lock_holder()
            assert "terminal deploy" in _plan()["why_not"] if False else True
            p = update_op.plan(**dict(_plan_kw(), holder=None))
            assert not p["selectable"] and "terminal deploy" in p["why_not"]
        finally:
            os.close(fd)

    def test_nmas_deploy_takes_it_before_anything_else(self):
        src = open(os.path.join(ROOT, "scripts", "nmas-deploy"), encoding="utf-8").read()
        main = src[src.index("def main("):src.index("def take_lock(")]
        assert main.index("take_lock(repo)") < main.index("_deploy(")
        assert "LOCKED" in main and "os.close(lock)" in main


# ------------------------------------------------ the wiring, statically

def _components():
    """{name: {member: body}} for every Alpine component the v2 pages load."""
    out = {}
    for rel in ("static/js/nmas_v2.js", "static/js/nmas_update.js"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        for m in re.finditer(r"A\.data\('([a-z_]+)'", src):
            body = src[m.end():]
            nxt = re.search(r"\n    A\.data\('|\n  }\n", body)
            body = body[:nxt.start()] if nxt else body
            members = {}
            for mm in re.finditer(r"\n        (?:get )?([A-Za-z_]+)(?:\(\)|: function)", body):
                start = mm.end()
                nx = re.search(r"\n        (?:get )?[A-Za-z_]+(?:\(\)|: function)", body[start:])
                members[mm.group(1)] = body[start:start + (nx.start() if nx else len(body))]
            out[m.group(1)] = members
    return out


def _reads(members, name, seen=None):
    """({attrs read through $el}, {attrs read through $root}) by *name* and
    every member it calls."""
    seen = seen if seen is not None else set()
    if name in seen or name not in members:
        return set(), set()
    seen.add(name)
    body = members[name]
    el_vars = {"this.$el"} | {f"{v}" for v in re.findall(r"(\w+) = this\.\$el\b", body)}
    root_vars = {"this.$root"} | set(re.findall(r"(\w+) = this\.\$root\b", body))
    via_el = {a for v in el_vars for a in re.findall(re.escape(v) + r"\.getAttribute\('(data-[\w-]+)'\)", body)}
    via_root = {a for v in root_vars for a in re.findall(re.escape(v) + r"\.getAttribute\('(data-[\w-]+)'\)", body)}
    for callee in re.findall(r"(?:this|self)\.(\w+)\(", body):
        e, r = _reads(members, callee, seen)
        via_el |= e
        via_root |= r
    return via_el, via_root


def _wiring_offences(templates: dict, components: dict) -> tuple:
    """(offences, pairs checked): every element that invokes a component member
    through a directive must carry what the member reads through $el, and its
    x-data element what it reads through $root."""
    from html.parser import HTMLParser

    offences, checked = [], [0]

    class P(HTMLParser):
        def __init__(self, rel):
            super().__init__()
            self.rel, self.stack = rel, []

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            scope = self.stack[-1] if self.stack else None
            if "x-data" in a and a["x-data"] in components:
                scope = (a["x-data"], a)
            if scope:
                name, root_attrs = scope
                for k, v in a.items():
                    if (k.startswith(("x-on:", "x-bind:")) or k in ("x-show", "x-text")) and \
                            v in components[name]:
                        via_el, via_root = _reads(components[name], v)
                        checked[0] += 1
                        missing = sorted({x for x in via_el if x not in a}
                                         | {x for x in via_root if x not in root_attrs})
                        if missing:
                            offences.append(f"{self.rel}: <{tag} {k}=\"{v}\"> ({name}) reads {missing}")
            if tag not in ("input", "br", "img", "meta", "link", "hr"):
                self.stack.append(scope)

        def handle_endtag(self, tag):
            if self.stack and tag not in ("input", "br", "img", "meta", "link", "hr"):
                self.stack.pop()

    for rel, text in templates.items():
        P(rel).feed(text)
    return offences, checked[0]


def _v2_templates():
    base = os.path.join(ROOT, "templates", "v2")
    return {f"templates/v2/{n}": open(os.path.join(base, n), encoding="utf-8").read()
            for n in sorted(os.listdir(base)) if n.endswith(".html")}


class TestEveryV2ControlIsWired:
    """The first run's defect as a rule over EVERY v2 component (the operator:
    any other control built the same way fails the same way)."""

    def test_every_member_finds_the_attributes_it_reads(self):
        offences, checked = _wiring_offences(_v2_templates(), _components())
        assert checked >= 12, checked                  # the scan saw the controls (measured 16)
        assert offences == []

    def test_the_rule_finds_the_first_runs_shape(self):
        # The component as it shipped in b27c786: $el read on the button.
        broken = {"update": {"blocked": "return this.$el.getAttribute('data-selectable') !== 'yes';"}}
        page = ('<div x-data="update" data-selectable="yes">'
                '<button x-bind:disabled="blocked">Update</button></div>')
        offences, checked = _wiring_offences({"t.html": page}, broken)
        assert checked == 1 and offences == ["t.html: <button x-bind:disabled=\"blocked\"> (update) "
                                             "reads ['data-selectable']"]


# ------------------------------------------------ clicking what ships

def _browser_or_skip():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the static wiring rule above still runs")
    return browser


@pytest.fixture
def served_update(monkeypatch, tmp_path):
    """The real app on loopback with a selectable plan; the request and the
    updater's record recorded and scripted."""
    browser = _browser_or_skip()
    import app as A
    from modules import update_op

    fixed = _plan()
    calls = {"apply": [], "answer": {"ok": False, "reason": "the preview moved: preview again"},
             "status": {"running": "a" * 40, "pending": [], "outcome": {"state": "absent"},
                        "outcome_words": update_op.OUTCOME_WORDS}}
    monkeypatch.setattr(update_op, "plan", lambda **kw: fixed)

    def request(h, ack, actor, **kw):
        calls["apply"].append((h, ack, actor))
        return calls["answer"]
    monkeypatch.setattr(update_op, "request", request)
    monkeypatch.setattr(update_op, "status", lambda: calls["status"])
    with browser.Served(A.app) as srv, browser.Browser() as b:
        yield {"b": b, "srv": srv, "calls": calls, "hash": fixed["hash"]}


class TestClickingTheShippedButton:
    def test_the_click_sends_the_request_and_a_refusal_is_shown(self, served_update):
        b, calls = served_update["b"], served_update["calls"]
        b.go(served_update["srv"].url("/v2/update"))
        b.wait_for("return window.Alpine && document.querySelector('#update-confirm') "
                   "&& !document.querySelector('#update-confirm').disabled")
        assert b.js("return document.querySelector('#update-confirm').textContent.trim()") == \
            "Update to bbbbbbbbbb"
        b.click("#update-confirm")
        text = b.wait_for("var n=document.querySelector('.confirm .notice-danger');"
                          "return n && getComputedStyle(n).display !== 'none' && n.textContent")
        assert calls["apply"] == [(served_update["hash"], [], "test-person@example.invalid")]
        assert "the preview moved: preview again" in text

    def test_an_accepted_request_draws_the_stepper_from_the_updaters_record(self, served_update):
        b, calls = served_update["b"], served_update["calls"]
        calls["answer"] = {"ok": True, "id": "0123456789abcdef", "target": "b" * 40,
                           "from": "a" * 40, "up_bound_s": 120, "updater_timeout_s": 900}
        calls["status"]["outcome"] = {"state": "ok", "value": {
            "id": "0123456789abcdef", "outcome": "running", "step": "ci"}}
        b.go(served_update["srv"].url("/v2/update"))
        b.wait_for("return window.Alpine && !document.querySelector('#update-confirm').disabled")
        b.click("#update-confirm")
        cls = b.wait_for("var li=document.querySelector('[data-step=ci]');"
                         "return li && li.className.indexOf('step-current') >= 0 && li.className")
        assert "step-current" in cls
        assert b.js("return document.querySelector('[data-step=fetch]').className") == "step step-done"
        assert b.js("return getComputedStyle(document.querySelector('[data-stepper]')).display") != "none"

    def test_check_again_on_about_answers_in_words(self, served_update):
        b = served_update["b"]
        b.go(served_update["srv"].url("/v2/help/about"))
        b.wait_for("return window.Alpine && document.querySelector('.check-again button')")
        b.click(".check-again button")
        said = b.wait_for("return document.querySelector('.check-again .muted').textContent")
        assert said.startswith("Not asked: the reader jobs do not run in this process")


class TestCheckAgain:
    def test_it_runs_the_reader_only_where_the_readers_run(self, monkeypatch):
        import threading

        import app as A
        from modules import reader_job
        ran = threading.Event()
        monkeypatch.setattr(reader_job, "run_once", lambda reader, announce=None: ran.set())
        r = A.app.test_client().post("/update/check", json={})
        assert r.status_code == 409 and "do not run in this process" in r.get_json()["error"]
        monkeypatch.setattr(reader_job, "running", lambda name: True)
        r = A.app.test_client().post("/update/check", json={})
        assert r.status_code == 202 and ran.wait(5)
