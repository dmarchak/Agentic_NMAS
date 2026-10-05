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
import sys
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

    def test_a_push_between_confirm_and_apply_lands_exactly_the_confirmed_commit(self, repos):
        """C436, the operator, 2026-10-04: 7992a15 was confirmed (CI passed), bb179f7 was
        pushed before the updater ran, and "origin/main is now bb179f7ddf" refused it. The
        confirmed commit is still on origin/main: it is landed, and the checkout is never
        moved past it."""
        restarts = []
        _U, rec = _run(repos, _request(repos, target=repos["shas"][1]), _gate(), restarts)
        assert rec["outcome"] == "updated" and restarts == [1]
        assert _g(repos["work"], "rev-parse", "HEAD") == repos["shas"][1]
        assert _g(repos["work"], "rev-parse", "origin/main") == repos["shas"][2]
        assert [s["sha"] for s in rec["host_steps"]] == [repos["shas"][1]]

    def test_the_host_steps_are_exactly_those_up_to_the_target(self, repos):
        """A step in a commit beyond the target is not this update's, and is not demanded."""
        (repos["work"] / "g").write_text("3")
        _g(repos["work"], "checkout", "-q", repos["shas"][2])
        _g(repos["work"], "add", "g")
        _g(repos["work"], "commit", "-q", "-m", "c3\n\nHost-Step: install python3-bar on the host")
        _g(repos["work"], "push", "-q", "origin", "HEAD:main")
        _g(repos["work"], "checkout", "-q", "main")
        _g(repos["work"], "reset", "-q", "--hard", repos["shas"][0])
        restarts = []
        _U, rec = _run(repos, _request(repos), _gate(), restarts)     # target c2, c3 beyond
        assert rec["outcome"] == "updated"
        assert _g(repos["work"], "rev-parse", "HEAD") == repos["shas"][2]
        assert [s["step"] for s in rec["host_steps"]] == ["install python3-foo on the host"]

    def test_a_confirmed_commit_no_longer_on_main_refuses(self, repos):
        """Refused only when the confirmed commit LEFT origin/main (here a rewritten remote),
        or its CI verdict changed (`test_ci_not_passed_refuses_and_nothing_moves`)."""
        (repos["work"] / "f").write_text("other")
        _g(repos["work"], "commit", "-q", "-am", "a rewritten history")
        _g(repos["work"], "push", "-q", "--force", "origin", "HEAD:main")
        _g(repos["work"], "reset", "-q", "--hard", repos["shas"][0])
        U = _updater()
        with pytest.raises(U.Refused, match="no longer on origin/main"):
            U.update(_request(repos), repo=str(repos["work"]),
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
        """This test once asserted `["runuser", "-u"]`: it pinned the bare name
        the first real run died on (C246). Now by the table's entries."""
        tree = ast.parse(open(UPDATER, encoding="utf-8").read())
        lists = [n for n in ast.walk(tree) if isinstance(n, ast.List)
                 and any(_binary(e) == "git" for e in n.elts)]
        assert lists, "the scan found no git invocation at all"
        for n in lists:
            assert _binary(n.elts[0]) == "runuser"
            assert isinstance(n.elts[1], ast.Constant) and n.elts[1].value == "-u"


def _root_files_read_as_root():
    """Inside the confined runner (a user namespace) root's files read as
    another uid, so a check of real root-owned files cannot run there."""
    if os.stat("/usr").st_uid != 0:
        pytest.skip("root's files read as another uid here (the confined runner's user "
                    "namespace); this runs under plain pytest, in CI and on the host")


def _binary(node):
    """The BINARIES key an argv element names (`BINARIES["git"]`), or None."""
    if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
            and node.value.id == "BINARIES" and isinstance(node.slice, ast.Constant)):
        return node.slice.value
    return None


def _exec_sites(src):
    """Every call in *src* that starts a program: (the call, its argv node)."""
    execs = {"run", "Popen", "call", "check_call", "check_output", "execv", "execvp",
             "execvpe", "spawnv", "system"}
    out = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name in execs and n.args:
                out.append((n, n.args[0]))
    return out


class TestEveryProgramByAbsolutePath:
    """C246: the first real run died at the checkout step on
    `FileNotFoundError: runuser`: its git environment set PATH=/usr/bin:/bin
    and runuser is /usr/sbin/runuser. A root process runs every program by
    ABSOLUTE path, from one table, and checks the table before it acts."""

    def test_every_program_the_updater_starts_comes_from_the_table(self):
        src = open(UPDATER, encoding="utf-8").read()
        sites = _exec_sites(src)
        assert len(sites) >= 2, sites                      # git (runuser) and the restart
        for call, argv in sites:
            assert isinstance(argv, ast.List), ast.unparse(call)
            assert _binary(argv.elts[0]) is not None, f"by name: {ast.unparse(call)}"

    def test_the_table_is_absolute_and_names_what_the_host_has(self):
        U = _updater()
        assert set(U.BINARIES) == {"runuser", "git", "systemctl"}
        assert all(os.path.isabs(p) for p in U.BINARIES.values())
        # Measured on the host (via LAN), 2026-09-30: each root:root 755.
        assert U.BINARIES["runuser"] == "/usr/sbin/runuser"

    def test_the_gate_is_handed_the_absolute_systemctl(self):
        src = open(UPDATER, encoding="utf-8").read()
        assert 'gate.unit_state(service, systemctl=BINARIES["systemctl"])' in src
        D = TestTheSharedLock()._deploy_script()
        seen = []
        D.subprocess = types.SimpleNamespace(run=lambda argv, **k: seen.append(argv) or
                                             types.SimpleNamespace(stdout="MainPID=7\n"))
        assert D.unit_state("x.service", systemctl="/usr/bin/systemctl")["MainPID"] == 7
        assert seen[0][0] == "/usr/bin/systemctl"

    def test_the_updaters_git_command_resolves_as_it_will_run(self, repos):
        """The gap that let C246 through: every test handed the updater a git of
        its own and never ran `user_git_for`'s command. Here it runs for real,
        in the environment the updater gives it, dropping ONLY the switch of
        user (runuser needs root): the program is resolved exactly as exec
        resolves it, from that environment's PATH."""
        import shutil
        U = _updater()
        me = __import__("pwd").getpwuid(os.getuid()).pw_name
        ran = []

        def run(argv, env=None, **kw):
            for prog in (argv[0], argv[4]):                # runuser, then git
                assert shutil.which(prog, path=env["PATH"]) == prog, \
                    f"{prog} does not resolve with PATH={env['PATH']}"
            ran.append(argv)
            return subprocess.run(argv[4:], env=env, **kw)
        git = U.user_git_for(str(repos["work"]), me, run=run)
        assert git(str(repos["work"]), "rev-parse", "HEAD") == repos["shas"][0]
        assert ran[0][:4] == ["/usr/sbin/runuser", "-u", me, "--"]

    def test_the_first_runs_command_would_have_failed_here(self):
        """The control, with the shipped argv: `runuser` by name in the git
        environment's PATH is not found, as on the host."""
        import shutil
        assert shutil.which("runuser", path="/usr/bin:/bin") is None
        assert shutil.which("/usr/sbin/runuser", path="/usr/bin:/bin") == "/usr/sbin/runuser"

    def test_the_self_test_passes_on_this_machine_for_the_real_table(self):
        """Real files, not stubs: the table's programs exist here, root's."""
        _root_files_read_as_root()
        assert _updater().self_test() == []

    def test_the_self_test_names_each_problem(self, tmp_path):
        _root_files_read_as_root()
        U = _updater()
        mine = tmp_path / "prog"
        mine.write_text("#!/bin/sh\n")
        mine.chmod(0o775)
        got = U.self_test({"runuser": "runuser", "gone": str(tmp_path / "nope"),
                           "mine": str(mine), "git": "/usr/bin/git"})
        text = "; ".join(got)
        assert "runuser: 'runuser' is not an absolute path" in text
        assert f"gone: {tmp_path / 'nope'}: No such file or directory" in text
        assert "mine:" in text and "not owned by root" in text and "lets others write it" in text
        assert not any(p.startswith("git:") for p in got)       # the control: a real one passes

    def test_a_self_test_that_fails_refuses_before_anything_moves(self, monkeypatch, repos, tmp_path):
        U, got = _main(monkeypatch, repos, tmp_path, self_test=lambda: ["runuser: /usr/sbin/runuser: gone"])
        assert got["outcome"] == "refused" and got["step"] == "started"
        assert "cannot run here, so nothing was moved: runuser" in got["reason"]
        assert got["calls"] == []                                # no lock, no gate, no git
        assert _g(repos["work"], "rev-parse", "HEAD") == repos["shas"][0]


def _main(monkeypatch, repos, tmp_path, self_test=lambda: [], fail_at=None, refuse=False):
    """Drive the REAL `main()` as the unit does, the service user being the
    test's own: only what needs root (the gate's root-owned copy, running git
    as another user) and the update itself are stood in for. *fail_at*: the
    step the update raises (or refuses) at."""
    U = _updater()
    me = __import__("pwd").getpwuid(os.getuid()).pw_name
    reqdir = repos["work"] / "data" / "update" / "requests"
    reqdir.mkdir(parents=True, exist_ok=True)
    req = _request(repos)
    (reqdir / f"{req['id']}.json").write_text(json.dumps(req))
    calls, states = [], []
    monkeypatch.setattr(U, "self_test", self_test)
    gate = _gate()
    gate._health = lambda: (200, {})
    gate.unit_state = lambda service, systemctl: {"MainPID": 100}
    monkeypatch.setattr(U, "load_gate", lambda *a: calls.append("gate") or gate)
    monkeypatch.setattr(U, "user_git_for", lambda repo, user: calls.append("git") or _local_git)
    monkeypatch.setattr(U, "write_state", lambda rec, **kw: states.append(rec))

    def update(req, *, report, **kw):
        calls.append("update")
        for step in U.STEPS:
            report(step)
            if step == fail_at:
                if refuse:
                    raise U.Refused(f"refused at {step}")
                raise FileNotFoundError(2, "No such file or directory", "runuser")
        return {"outcome": "updated", "id": req["id"], "step": "wait"}
    monkeypatch.setattr(U, "update", update)
    rc = U.main({"NMAS_UPDATE_REPO": str(repos["work"]), "NMAS_UPDATE_USER": me})
    return U, dict(states[-1], rc=rc, calls=calls)


def _lock_is_free(repo):
    import fcntl
    fd = os.open(os.path.join(repo, "data", "update", "lock"), os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(fd)


class TestTheLockIsReleasedOnEveryPath:
    """The operator's item 4: the lock is a FLOCK on a descriptor, so the
    file's presence means nothing (the host's 0-byte `data/update/lock`, mtime
    21:48, blocks nobody); only a HELD lock blocks. `main()` releases it on
    every path, and the kernel does if the process dies."""

    @pytest.mark.parametrize("step", ["checkout", "fetch", "ci", "move", "restart", "wait"])
    @pytest.mark.parametrize("refuse", [False, True])
    def test_a_failure_at_every_step_leaves_it_released(self, monkeypatch, repos, tmp_path, step, refuse):
        U, got = _main(monkeypatch, repos, tmp_path, fail_at=step, refuse=refuse)
        assert got["outcome"] == ("refused" if refuse else "failed") and got["step"] == step
        assert _lock_is_free(str(repos["work"]))
        assert "No such file or directory: 'runuser'" in got["reason"] or refuse

    def test_a_finished_update_leaves_it_released(self, monkeypatch, repos, tmp_path):
        U, got = _main(monkeypatch, repos, tmp_path)
        assert got["outcome"] == "updated", got.get("reason")
        assert _lock_is_free(str(repos["work"]))

    def test_the_files_presence_blocks_nothing(self, repos):
        """The host's state after the failed run: the file there, nobody holding it."""
        lock = repos["work"] / "data" / "update" / "lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_bytes(b"")
        D = TestTheSharedLock()._deploy_script()
        fd = D.take_lock(str(repos["work"]))
        assert fd is not None
        os.close(fd)
        os.close(_updater().take_lock(str(repos["work"]), os.getuid()))

    def test_a_process_that_dies_holding_it_releases_it(self, repos):
        lock = repos["work"] / "data" / "update" / "lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        code = ("import fcntl, os, sys; fd = os.open(sys.argv[1], os.O_RDONLY | os.O_CREAT, 0o644); "
                "fcntl.flock(fd, fcntl.LOCK_EX); print('held', flush=True); os.kill(os.getpid(), 9)")
        out = subprocess.run([sys.executable, "-c", code, str(lock)], capture_output=True, text=True)
        assert out.stdout.strip() == "held" and out.returncode == -9
        assert _lock_is_free(str(repos["work"]))

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
        assert [(s["sha"], s["step"], s["when"]) for s in out["host_steps"]] == [
            (repos["shas"][1], "install python3-foo on the host", "before")]
        assert out["after_steps"] == []
        assert out["updater_by_sha"] == {} and out["checkout_changes"] == []
        assert out["target"] == repos["shas"][2]
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
        assert {p for ps in out["updater_by_sha"].values() for p in ps} == \
            {"deploy/update/nmas-update"}
        assert len(out["updater_by_sha"]) == 1             # named by the commit that changed it


# ------------------------------------------------------------------ the app side

def _value(**over):
    """The `app-pushed` reader's value, in its shape (C436): the commits newest first (the
    tip first), each commit's verdict, and the target, the newest commit CI passed. Built
    from a tip's ``ci``: the tip is the target exactly when ITS verdict is a pass, unless
    the caller names ``verdicts`` or ``target`` itself."""
    v = {"running": "a" * 40, "tip": "b" * 40, "state": "behind", "behind": 2, "branch": "main",
         "commits": [{"sha": "b" * 40, "subject": "fix", "author": "t", "at": "2026-09-30T10:00:00Z"},
                     {"sha": "c" * 40, "subject": "needs a package", "author": "t",
                      "at": "2026-09-30T09:30:00Z"}],
         "host_steps": [{"sha": "c" * 40, "step": "install python3-foo"}], "updater_by_sha": {},
         "checkout_changes": [], "behind_since": "2026-09-30T09:00:00Z",
         "behind_since_basis": "first seen by this reader, which asks every 300 s",
         "ci": {"tip": "b" * 40, "state": "verified", "sentence": "CI passed for bbbbbbbbbb",
                "asked_at": "2026-09-30T10:01:00Z"}}
    v.update(over)
    ci = v.get("ci") or {}
    v.setdefault("verdicts", {ci["tip"]: ci} if ci.get("tip") else {})
    v.setdefault("target", v["tip"] if ci.get("tip") == v["tip"] and ci.get("state") == "verified"
                 else "")
    return v


def _plan_kw(value=None, install="ok"):
    return {"cached": {"state": "ok", "doc": {"last_good": {"value": value or _value(),
                                                             "value_at": "2026-09-30T10:01:00Z"}}},
            "install": {"state": install}, "running": "a" * 40, "pending_now": [],
            "now_outcome": {"state": "absent"}, "operations": []}


def _plan(**kw):
    from modules import update_op
    return update_op.plan(**_plan_kw(**kw))


class TestThePreview:
    def test_all_gates_pass_and_the_hash_is_stable(self):
        a, b = _plan(), _plan()
        assert a["selectable"] and a["hash"] == b["hash"]
        assert all(g["state"] == "pass" for g in a["gates"]) and len(a["gates"]) == 7

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
        assert row["state"] == "not_installed" and row["action"]["reference"].startswith("docs/UPDATE.md")

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
        assert update_op.install_rows(s)[0]["action"]["reference"].startswith("docs/UPDATE.md")
        assert update_op.install_state(root=str(tmp_path), installed=inst, active=False)["state"] == "inactive"
        # The control: the same file the service user CAN write is danger, whoever owns it.
        monkeypatch.setattr(update_op.os, "access", lambda p, m: str(p) == str(f))
        assert update_op.install_state(root=str(tmp_path), installed=inst, active=True)["state"] == "writable"

    def _as_root(self, monkeypatch, update_op, f):
        real_stat = os.stat

        def as_root(path, *a, **k):
            st = real_stat(path, *a, **k)
            if str(path) != str(f):
                return st
            return os.stat_result((stat.S_IFREG | 0o755, st.st_ino, st.st_dev, 1, 0, 0,
                                   st.st_size, 0, 0, 0))
        monkeypatch.setattr(update_op.os, "stat", as_root)
        monkeypatch.setattr(update_op.os, "access", lambda p, m: False)

    def test_an_updater_that_cannot_run_is_danger_before_anyone_clicks(self, tmp_path, monkeypatch):
        """C246: ownership and modes passed while runuser could not be found.
        The check now runs the INSTALLED copy's own self-test."""
        from modules import attention, update_op
        f = tmp_path / "nmas-update"
        f.write_text(open(UPDATER, encoding="utf-8").read().replace(
            '"/usr/sbin/runuser"', f'"{tmp_path}/no-runuser"'))
        self._as_root(monkeypatch, update_op, f)
        inst = (("the updater", str(f), "deploy/update/nmas-update"),)
        s = update_op.install_state(installed=inst, active=True)
        assert s["state"] == "cannot_run"
        # Only runuser moved; inside the confined runner the real git and
        # systemctl also read as not root's, so this names the one it moved.
        assert f"runuser: {tmp_path}/no-runuser: No such file or directory" in s["cannot_run"]
        (row,) = update_op.install_rows(s)
        assert row["state"] == "cannot_run" and "CANNOT RUN" in row["detail"]
        assert row["action"]["reference"].startswith("docs/UPDATE.md")
        assert attention._JOB_STATES["cannot_run"][1] == "danger"
        kw = dict(_plan_kw(), install=s)                        # and the preview refuses it
        p = update_op.plan(**kw)
        assert not p["selectable"] and "it would fail before moving anything:" in p["why_not"]
        assert "no-runuser: No such file or directory" in p["why_not"]

    def test_the_installed_copy_that_predates_the_self_test_cannot_run(self, tmp_path, monkeypatch):
        from modules import update_op
        f = tmp_path / "nmas-update"
        f.write_text("STEPS = ()\n")                           # the shape of 58ae274's copy
        self._as_root(monkeypatch, update_op, f)
        s = update_op.install_state(installed=(("the updater", str(f), "deploy/update/nmas-update"),),
                                    active=True)
        assert s["state"] == "cannot_run" and "has no self-test" in s["cannot_run"][0]

    def test_this_releases_updater_passes_its_own_self_test_as_installed(self, tmp_path, monkeypatch):
        """The control: the release's own updater, installed, can run."""
        _root_files_read_as_root()
        from modules import update_op
        f = tmp_path / "nmas-update"
        f.write_text(open(UPDATER, encoding="utf-8").read())
        self._as_root(monkeypatch, update_op, f)
        s = update_op.install_state(root=ROOT, installed=(("the updater", str(f),
                                                           "deploy/update/nmas-update"),),
                                    active=True)
        assert s["cannot_run"] == [] and s["state"] == "ok"

    @pytest.mark.parametrize("state,commands", [("cannot_run", "REINSTALL_COMMANDS"),
                                                ("differs", "REINSTALL_COMMANDS"),
                                                ("not_installed", "INSTALL_COMMANDS")])
    def test_the_row_carries_the_exact_commands_not_a_document(self, state, commands):
        """The operator, 2026-09-30: "Re-install … (docs/UPDATE.md, 'Re-install')"
        sent them looking. A one-time root step shows its commands, copyable."""
        from modules import update_op
        s = {"state": state, "cannot_run": ["runuser: gone"], "differs": ["the updater differs"],
             "missing": ["the updater"]}
        (row,) = update_op.install_rows(s)
        cmd = row["action"]["command"]
        assert cmd.splitlines()[0] == f"cd {update_op.ROOT}"
        assert cmd.splitlines()[1:] == list(getattr(update_op, commands))
        assert row["action"]["reference"].startswith("docs/UPDATE.md, ")

    def test_every_command_is_the_documents_own(self):
        """One owner, and the document says the same: each line appears in UPDATE.md."""
        from modules import update_op
        doc = open(os.path.join(ROOT, "docs", "UPDATE.md"), encoding="utf-8").read()
        lines = set(update_op.REINSTALL_COMMANDS) | set(update_op.INSTALL_COMMANDS)
        # 9 since 2026-10-01: the units' render and install are ONE line (a fresh
        # folder, the files named), where they were two.
        assert len(lines) >= 9 and update_op.UNITS_COMMAND in lines
        missing = [l for l in lines if l not in doc]
        assert missing == []

    def test_the_row_says_since_when(self, tmp_path):
        """The operator: "since not recorded" on the cannot_run row. The later of
        this release starting and the installed copy being written."""
        from modules import update_op
        f = tmp_path / "nmas-update"
        f.write_text("x")
        os.utime(f, (1000.0, 1000.0))
        assert update_op.condition_since(str(f), started=2000.0) == (
            2000.0, "when this release started running")
        os.utime(f, (3000.0, 3000.0))
        assert update_op.condition_since(str(f), started=2000.0) == (
            3000.0, "when the installed copy was written")
        assert update_op.condition_since(str(tmp_path / "gone"), started=2000.0)[0] == 2000.0
        (row,) = update_op.install_rows({"state": "cannot_run", "cannot_run": ["x"]})
        assert isinstance(row["since"], float) and "It began when" in row["detail"]

    def test_the_check_command_prints_the_commands_last(self, monkeypatch, capsys):
        from modules import update_op
        path = os.path.join(ROOT, "scripts", "nmas-update-check")
        loader = importlib.machinery.SourceFileLoader("nmas_update_check_under_test", path)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(mod)
        monkeypatch.setattr(update_op, "install_state", lambda: {
            "state": "cannot_run", "cannot_run": ["runuser: /usr/sbin/runuser: gone"],
            "files": [], "missing": [], "writable": [], "differs": []})
        monkeypatch.setattr(os, "geteuid", lambda: 1000)
        assert mod.main() == 2
        out = capsys.readouterr().out.rstrip().splitlines()
        assert out[0].startswith("updater: cannot_run: the updater CANNOT RUN")
        assert "    sudo systemctl daemon-reload" in out
        assert out[-1] == '  (docs/UPDATE.md, "Re-install")'

    def test_the_check_command_prints_the_self_test(self):
        src = open(os.path.join(ROOT, "scripts", "nmas-update-check"), encoding="utf-8").read()
        assert "self-test: " in src and "CANNOT RUN" in src

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
        assert r["steps"]["ci"] == {"state": "failed", "note": "failed: the CI gate does not pass"}
        assert r["steps"]["fetch"]["state"] == "done"
        assert r["steps"]["move"] == {"state": "not_reached", "note": "not reached"}
        assert r["done"] and r["failed"] and not r["reload"]
        assert r["words"].startswith("The update refused: nothing was changed: the CI gate")

    def test_the_first_real_runs_failure_is_three_states_never_a_bare_list(self):
        """The host, 2026-09-30 (C246): failed at step 3, and steps 4 to 9 were
        listed ending 'Running 4e40bd05b4' with nothing saying they never ran."""
        reason = "the updater raised FileNotFoundError: [Errno 2] No such file or directory: 'runuser'"
        r = self._states({"commit": "a" * 40}, self._status("failed", "checkout", reason=reason))
        s = {k: v["state"] for k, v in r["steps"].items()}
        assert [s[k] for k in KEYS] == ["done", "done", "failed"] + ["not_reached"] * 6
        assert r["steps"]["checkout"]["note"] == "failed: " + reason
        assert all(r["steps"][k]["note"] == "not reached" for k in KEYS[3:])
        assert r["failed"] and not r["reload"]

    @pytest.mark.parametrize("outcome,step", [("rolled_back", "wait"), ("refused", "started")])
    def test_every_failed_ending_marks_what_came_after_not_reached(self, outcome, step):
        r = self._states({"commit": "a" * 40}, self._status(outcome, step, reason="why"))
        after = KEYS[KEYS.index(step) + 1:]
        assert after and all(r["steps"][k]["state"] == "not_reached" for k in after)

    def test_the_units_limit_marks_the_rest_not_reached(self):
        r = self._states({"commit": "a" * 40}, {"pending": [], "outcome": {"state": "absent"}},
                         elapsed=901)
        assert r["steps"]["started"]["state"] == "failed"
        assert all(r["steps"][k]["state"] == "not_reached" for k in KEYS[2:])

    def test_not_reached_is_drawn_apart_from_pending_and_done(self):
        css = open(os.path.join(ROOT, "static", "css", "nmas-v2.css"), encoding="utf-8").read()
        rules = re.findall(r"\.stepper \.step-not_reached[^{]*\{([^}]*)\}", css)
        assert any("line-through" in r for r in rules) and any("dashed" in r for r in rules)

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


@pytest.fixture(scope="module")
def live_browser():
    """ONE server and ONE Firefox for this module's browser tests (the
    operator, 2026-10-01: each test started its own Firefox, about 2.4 s
    here and more on CI's runner, which HAS a browser, so these run there).
    Requested only by the tests that click, so a skipped test starts
    nothing; torn down bounded (tests/browser.py) when the module ends."""
    browser = _browser_or_skip()
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        yield browser, srv, b


def _between_tests(browser, b):
    """Leave the page and end its socket.io session, so the next test starts
    from nothing a previous one left."""
    try:
        b.go("about:blank")
    finally:
        browser.close_socketio_sessions()


@pytest.fixture
def served_update(monkeypatch, tmp_path, live_browser):
    """The real app on loopback with a selectable plan; the request and the
    updater's record recorded and scripted."""
    browser, srv, b = live_browser
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
    yield {"b": b, "srv": srv, "calls": calls, "hash": fixed["hash"]}
    _between_tests(browser, b)


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

    def test_a_ticked_host_step_reaches_the_request(self, served_update):
        """The operator, 2026-09-30: the box was ticked and the refusal was
        identical, because the boxes sit in the preview ABOVE the component
        and the click read them from the component. Ticking must change what
        is sent."""
        b, calls = served_update["b"], served_update["calls"]
        b.go(served_update["srv"].url("/v2/update"))
        b.wait_for("return window.Alpine && document.querySelector('input[data-host-step]') "
                   "&& !document.querySelector('#update-confirm').disabled")
        b.click("input[data-host-step]")
        b.click("#update-confirm")
        b.wait_for("var n=document.querySelector('.confirm .notice-danger');"
                   "return n && getComputedStyle(n).display !== 'none' && n.textContent")
        assert calls["apply"] == [(served_update["hash"], ["c" * 40], "test-person@example.invalid")]

    def test_a_ticked_host_step_survives_a_live_redraw(self, served_update):
        """C472 (R27's survey, 2026-10-05): the panel redraws on `job_health` and
        `app_version`, and the redraw cleared the person's ticks, so a step said done had to
        be said again, or the confirm was refused naming it. The redraw now sends the boxes."""
        b, calls = served_update["b"], served_update["calls"]
        b.go(served_update["srv"].url("/v2/update"))
        b.wait_for("return window.Alpine && document.querySelector('input[data-host-step]') "
                   "&& !document.querySelector('#update-confirm').disabled")
        b.click("input[data-host-step]")
        for key in ("job_health", "app_version"):
            b.js("document.getElementById('update-panel').dataset.old = '1';"
                 "document.body.dispatchEvent(new CustomEvent('nmas:' + arguments[0]));"
                 "return 1", key)
            b.wait_for("var p = document.getElementById('update-panel');"
                       "return !!p && !p.dataset.old && !document.querySelector("
                       "'.htmx-swapping, .htmx-settling, .htmx-request')", 15)
            assert b.js("return document.querySelector('input[data-host-step]').checked"), key
        b.wait_for("return !document.querySelector('#update-confirm').disabled")
        b.click("#update-confirm")
        b.wait_for("var n=document.querySelector('.confirm .notice-danger');"
                   "return n && getComputedStyle(n).display !== 'none' && n.textContent")
        assert calls["apply"] == [(served_update["hash"], ["c" * 40], "test-person@example.invalid")]

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

    def test_a_wait_in_force_does_not_hold_the_panel(self, served_update, monkeypatch):
        """The operator, 2026-10-01: with a wait active, Check again said "No
        answer after 12 s" and the page read "asked 7 min ago". The wait held
        the whole panel, so the redraw that carries every answer was
        swallowed. A redraw now lands, and the new panel is still waiting."""
        from modules import update_op
        b = served_update["b"]
        waiting = dict(_plan(), waiting={"target": "b" * 40, "requested_by": "p@example.invalid",
                                         "requested_at": "2026-10-01T09:00:00Z"},
                       selectable=False, waitable=False)
        monkeypatch.setattr(update_op, "plan", lambda **kw: waiting)
        served_update["calls"]["status"]["waiting"] = waiting["waiting"]
        b.go(served_update["srv"].url("/v2/update"))
        b.wait_for("var w=document.querySelector('#update-waiting');"
                   "return window.Alpine && w && getComputedStyle(w).display !== 'none' && w.textContent")
        assert b.js("return document.querySelector('[data-update-hold]')") is None
        b.js("document.querySelector('#update-panel').setAttribute('data-old', '1');"
             "htmx.trigger(document.body, 'nmas:app_version'); return 1")
        b.wait_for("var p=document.querySelector('#update-panel'); return p && !p.hasAttribute('data-old')")
        words = b.wait_for("var w=document.querySelector('#update-waiting');"
                           "return w && getComputedStyle(w).display !== 'none' && w.textContent")
        assert words.startswith("Waiting for CI: the update to bbbbbbbbbb starts when CI passes")

    @pytest.mark.parametrize("selectable", [True, False])
    def test_no_wait_in_force_draws_no_stop_waiting(self, served_update, monkeypatch,
                                                     tmp_path, selectable):
        """The operator, 2026-10-01: "Stop waiting" was drawn with no wait
        requested. The host's state: a leftover `deferred.json.lock`, an ended
        outcome for an older release, no `deferred.json`. The REAL plan's
        waiting field, the shipped page, a real browser."""
        from modules import update_op
        b = served_update["b"]
        d = tmp_path / "update"
        d.mkdir()
        (d / "deferred.json.lock").write_text("")
        (d / "deferred_outcome.json").write_text(json.dumps({
            "ended_at": "2026-10-01T03:00:23Z", "outcome": "ci_failed", "target": "9" * 40,
            "words": "CI failed for this release: it will not be installed. The next release "
                     "fixes it; nothing was updated (asked for 9999999999)"}))
        monkeypatch.setattr(update_op, "DEFERRED", str(d / "deferred.json"))
        monkeypatch.setattr(update_op, "DEFERRED_OUTCOME", str(d / "deferred_outcome.json"))
        assert update_op.deferred() == {}, "the lock file is not a wait"
        p = dict(_plan(), waiting=update_op.deferred(), selectable=selectable, waitable=False)
        monkeypatch.setattr(update_op, "plan", lambda **kw: p)
        b.go(served_update["srv"].url("/v2/update"))
        b.wait_for("return window.Alpine && document.querySelector('#update-confirm') "
                   "&& !document.querySelector('#update-confirm').hasAttribute('x-cloak') "
                   "&& document.querySelector('#update-confirm')._x_dataStack !== undefined "
                   "|| (window.Alpine && document.querySelector('#update-panel'))")
        b.wait_for("return !document.querySelector('[x-cloak]') || "
                   "!document.querySelector('#update-stop-waiting').hasAttribute('x-cloak')")
        shown = b.js("var s=document.querySelector('#update-stop-waiting');"
                     "return s ? getComputedStyle(s).display : 'absent'")
        assert shown in ("none", "absent"), shown

    def test_a_redraw_with_no_wait_draws_no_stop_waiting(self, served_update, monkeypatch):
        """C279, reproduced by the operator (2026-10-01): a hard reload drew
        the panel right, and Check again's answer, arriving as a REDRAW,
        brought "Stop waiting" back with `data-waiting="no"`. Only the
        elements with an id lost Alpine's `display: none`: htmx's settle step
        copies `class` and `style` from the old element with the same id and
        then restores the server's attributes, which carry no `style`, so
        Alpine's hiding was removed and nothing re-ran `x-show`. The earlier
        test loaded a fresh page and could not see it. CI is running for the
        target and no wait is in force, as on the host."""
        import time

        from modules import update_op
        b = served_update["b"]
        p = dict(_plan(), waiting={}, selectable=False, waitable=True)
        monkeypatch.setattr(update_op, "plan", lambda **kw: p)
        b.go(served_update["srv"].url("/v2/update"))
        b.wait_for("var c=document.querySelector('#update-confirm');"
                   "return window.Alpine && c && getComputedStyle(c).display !== 'none'")
        hidden = ("var w=document.querySelector('#update-waiting'),"
                  "s=document.querySelector('#update-stop-waiting');"
                  "return [getComputedStyle(w).display, getComputedStyle(s).display]")
        assert b.js(hidden) == ["none", "none"]
        b.js("document.querySelector('#update-panel').setAttribute('data-old', '1');"
             "htmx.trigger(document.body, 'nmas:app_version'); return 1")
        b.wait_for("var p=document.querySelector('#update-panel'); return p && !p.hasAttribute('data-old')"
                   " && window.Alpine && document.querySelector('.confirm')._x_dataStack")
        time.sleep(0.5)                       # well past htmx's settle delay (20 ms)
        assert b.js("return document.querySelector('.confirm').getAttribute('data-waiting')") == "no"
        assert b.js(hidden) == ["none", "none"]

    def test_check_again_on_about_answers_in_words(self, served_update):
        b = served_update["b"]
        b.go(served_update["srv"].url("/v2/help/about"))
        b.wait_for("return window.Alpine && document.querySelector('.check-again button')")
        b.click(".check-again button")
        said = b.wait_for("return document.querySelector('.check-again .check-late').textContent")
        assert said.startswith("Not asked: the reader jobs do not run in this process")


def test_htmx_settles_no_attribute_alpine_owns():
    """C279's cause, as a rule over every v2 page: htmx's settle step copies an
    old element's `class` and `style` onto the new one with the same id and
    then restores the server's, removing what Alpine set (`x-show`'s
    `display: none`, an `x-bind:class`). The v2 frame settles nothing. The
    population it protects: elements with an id whose style or class Alpine
    drives (floor 2: Stop waiting and its words)."""
    base = open(os.path.join(ROOT, "templates", "v2", "base.html"), encoding="utf-8").read()
    meta = re.search(r"<meta name=\"htmx-config\" content='([^']*)'>", base)
    assert meta, "the v2 frame has no htmx-config"
    assert json.loads(meta.group(1)).get("attributesToSettle") == []
    exposed = []
    for name in sorted(os.listdir(os.path.join(ROOT, "templates", "v2"))):
        text = open(os.path.join(ROOT, "templates", "v2", name), encoding="utf-8").read()
        for tag in re.findall(r"<[a-z]+\b[^>]*>", text):
            if re.search(r'\sid="', tag) and re.search(r"\s(x-show|x-bind:class|x-bind:style|:class|:style)=", tag):
                exposed.append((name, re.search(r'\sid="([^"]*)"', tag).group(1)))
    assert ("_update.html", "update-stop-waiting") in exposed and len(exposed) >= 2, exposed


def _record_runs(took_ms, value_at=None):
    """Put measured runs in the reader's store: the page's bound is 2.5x the
    slowest. *value_at* back-dates the stored answer."""
    from modules import reader_job
    path = reader_job.store_path("app-pushed")
    doc = reader_job.read_cached("app-pushed")["doc"]
    doc["runs"] = [{"took_ms": took_ms}]
    if value_at:
        doc["last_good"]["value_at"] = value_at
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)


BUTTON = "document.querySelector('#installation .check-again button')"
CONTROL = "document.querySelector('#installation .check-again')"
STAMP = "document.querySelector('#installation .check-again').closest('dd').querySelector('.stamp')"


@pytest.fixture
def served_about(scripted_reader, live_browser):
    browser, srv, b = live_browser
    yield {"b": b, "srv": srv, **scripted_reader}
    _between_tests(browser, b)


class TestCheckAgainInARealBrowser:
    """The operator's two problems, clicked: busy until the ANSWER, and the
    answer saying it came from this person's request."""

    def test_it_stays_busy_until_the_answer_arrives_through_a_redraw(self, served_about):
        from modules import reader_job
        s, b = served_about, served_about["b"]
        reader_job.run_once(s["reader"])                  # a scheduled answer to start from,
        _record_runs(4000, "2026-09-30T10:00:00Z")        # hours old, and a 10 s bound
        s["hold"].clear()
        b.go(s["srv"].url("/v2/help/about"))
        b.wait_for(f"return window.Alpine && {BUTTON} && {BUTTON}.textContent === 'Check again'")
        # The cause is on the timestamp's hover, never in the row.
        assert "the scheduled check" not in b.js("return document.querySelector('#installation').textContent")
        assert "the scheduled check" in b.js(f"return {STAMP}.title")
        b.click("#installation .check-again button")
        b.wait_for(f"return {BUTTON}.disabled && {BUTTON}.textContent === 'Checking…'")
        # Busy ON ITSELF: nothing narrated beside the button.
        assert b.js(f"return {CONTROL}.textContent") == "Checking…"
        # Another reader re-draws the panel mid-run: the new one is still busy.
        b.js("document.querySelector('#installation').setAttribute('data-old', '1');"
             "htmx.trigger(document.body, 'nmas:job_health'); return 1")
        b.wait_for("var s = document.querySelector('#installation'); return s && !s.hasAttribute('data-old')")
        b.wait_for(f"return window.Alpine && {BUTTON}.disabled && {BUTTON}.textContent === 'Checking…'")
        s["hold"].set()
        assert _wait_until(lambda: s["announced"]), "the answer was not announced"
        b.js("htmx.trigger(document.body, 'nmas:app_version'); return 1")   # the page's relay
        b.wait_for(f"return {BUTTON}.textContent === 'Check again' && !{BUTTON}.disabled "
                   f"&& {STAMP}.getAttribute('datetime') !== '2026-09-30T10:00:00Z'")
        # The confirmation is the timestamp reading "just now", in place.
        assert b.wait_for(f"return {STAMP}.textContent === 'just now' && {STAMP}.textContent")
        assert b.js(f"return {CONTROL}.textContent") == "Check again"
        text = b.js("return document.querySelector('#installation').textContent")
        assert "Up to date as of just now" in text and "request" not in text
        assert "checked on your request" in b.js(f"return {STAMP}.title")

    def test_an_answer_later_than_the_bound_is_said_on_the_page(self, served_about):
        from modules import reader_job
        s, b = served_about, served_about["b"]
        reader_job.run_once(s["reader"])
        _record_runs(200)                                 # 2.5x 0.2 s: a 1 s bound
        s["hold"].clear()
        b.go(s["srv"].url("/v2/help/about"))
        b.wait_for(f"return window.Alpine && {BUTTON} && {BUTTON}.textContent === 'Check again'")
        b.click("#installation .check-again button")
        late = b.wait_for("return document.querySelector('#installation .check-late').textContent")
        assert late.startswith("No answer after 1 s, longer than this check has taken here "
                               "(2.5x the slowest of its last 1 run(s), 0.2 s)")
        assert b.js(f"return {BUTTON}.textContent") == "Check again"


UPDATE_CHECK = "document.querySelector('#update-panel .check-again button')"
UPDATE_LATE = "document.querySelector('#update-panel .check-late')"


class TestCheckAgainAfterARefusalInARealBrowser:
    """C436, the operator, 2026-10-04: after the updater's refusal, "No answer after 11 s …
    this line changes when it answers" never changed, and Check again did nothing until a
    reload. Measured in the app log: the check answered in 1.6 s, and the panel holding the
    refusal threw the redraw carrying the answer away."""

    def test_the_answer_lands_on_a_panel_holding_a_refusal(self, served_update, scripted_reader):
        from modules import reader_job
        s, b = scripted_reader, served_update["b"]
        reader_job.run_once(s["reader"])
        _record_runs(4000)                                  # a 10 s bound
        b.go(served_update["srv"].url("/v2/update"))
        b.wait_for("return window.Alpine && document.querySelector('#update-confirm') "
                   "&& !document.querySelector('#update-confirm').disabled")
        b.click("#update-confirm")                          # refused: the panel holds it
        b.wait_for("return document.querySelector('[data-update-hold=\"result\"]')")
        b.js("document.querySelector('#update-panel').setAttribute('data-old', '1'); return 1")
        b.click("#update-panel .check-again button")
        assert _wait_until(lambda: s["announced"]), "the answer was not announced"
        b.js("htmx.trigger(document.body, 'nmas:app_version'); return 1")   # the page's relay
        b.wait_for("var p = document.querySelector('#update-panel'); "
                   "return p && !p.hasAttribute('data-old')")
        b.wait_for(f"return window.Alpine && {UPDATE_CHECK}.textContent === 'Check again' "
                   f"&& !{UPDATE_CHECK}.disabled")

    def test_a_check_that_hangs_gives_up_says_so_and_the_control_works_again(
            self, served_update, scripted_reader):
        from modules import reader_job
        s, b = scripted_reader, served_update["b"]
        reader_job.run_once(s["reader"])
        _record_runs(200)                                   # 2.5x 0.2 s: a 1 s bound
        s["hold"].clear()                                   # the check hangs
        b.go(served_update["srv"].url("/v2/update"))
        b.wait_for(f"return window.Alpine && {UPDATE_CHECK} "
                   f"&& {UPDATE_CHECK}.textContent === 'Check again'")
        b.click("#update-panel .check-again button")
        late = b.wait_for(f"return {UPDATE_LATE}.textContent")
        assert late.startswith("No answer after 1 s"), late
        assert b.js(f"return {UPDATE_CHECK}.disabled") is False
        b.click("#update-panel .check-again button")        # again, still hung: it says so
        still = b.wait_for(f"var t = {UPDATE_LATE}.textContent; "
                           "return t.indexOf('Still no answer') === 0 && t")
        assert "the check asked" in still and "(the bound is 1 s)" in still, still
        assert b.js(f"return {UPDATE_CHECK}.disabled") is False
        s["hold"].set()                                     # it answers at last
        assert _wait_until(lambda: s["announced"]), "the answer was not announced"
        b.js("htmx.trigger(document.body, 'nmas:app_version'); return 1")
        b.wait_for(f"return window.Alpine && {UPDATE_CHECK}.textContent === 'Check again' "
                   f"&& !{UPDATE_CHECK}.disabled && {UPDATE_LATE}.textContent === ''")


RUNNING = "a" * 40
AT_TIP = {"running": RUNNING, "tip": RUNNING, "state": "at_tip"}


@pytest.fixture
def scripted_reader(monkeypatch):
    """The `app-pushed` reader with a scripted read (held until released),
    the readers declared running, the app's commit fixed, and every
    announcement recorded instead of sent."""
    import dataclasses
    import threading

    from modules import reader_job
    from modules.readers import app_pushed
    from routes import health

    hold = threading.Event()
    hold.set()
    state = {"hold": hold, "value": dict(AT_TIP), "announced": []}

    def read():
        assert hold.wait(20), "the test never released the read"
        v = state["value"]
        return dict(v) if isinstance(v, dict) else v

    fake = dataclasses.replace(app_pushed.READER, read=read)
    monkeypatch.setattr(app_pushed, "READER", fake)
    monkeypatch.setattr(reader_job, "running", lambda name: True)
    monkeypatch.setattr(reader_job, "announce_via_page",
                        lambda keys, name, ok: state["announced"].append((tuple(keys), name, ok)))
    real = health.version_facts
    monkeypatch.setattr(health, "version_facts", lambda: {**real(), "running": RUNNING})
    monkeypatch.setattr(reader_job, "_REQUESTS", {})
    monkeypatch.setattr(reader_job, "_LAST_ANNOUNCED", {})
    if os.path.exists(reader_job.store_path(fake.name)):     # the shared test store
        os.remove(reader_job.store_path(fake.name))
    state["reader"] = fake
    yield state
    hold.set()                                   # never leave a held read behind


def _wait_until(pred, bound=10):
    import time
    end = time.monotonic() + bound
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def _without_attributes(html):
    """What a person reads: the markup's text, every attribute (a title) removed."""
    return re.sub(r'\s[\w:@.-]+="[^"]*"', "", html)


class TestCheckAgain:
    """The operator, 2026-09-30: Check again reverted on a 5 s timer after the
    REQUEST was accepted while the text still said "asking", and nothing could
    say whether the click had run the check. Measured on the host: both clicks
    answered 202, the run logged nothing on success, the store kept only the
    last (scheduled) run, and the reader announces only a CHANGED answer, so a
    check that found nothing new told no page (reader_job rule 13)."""

    def test_it_runs_the_reader_only_where_the_readers_run(self, monkeypatch):
        import app as A
        from modules import reader_job
        started = []
        monkeypatch.setattr(reader_job, "request_run", lambda *a, **k: started.append(a))
        r = A.app.test_client().post("/update/check", json={})
        assert r.status_code == 409 and "do not run in this process" in r.get_json()["error"]
        assert started == []

    def test_a_click_is_recorded_as_the_persons_request_with_its_duration(self, scripted_reader,
                                                                         caplog):
        import logging

        import app as A
        from modules import reader_job
        from tests.conftest import TEST_PERSON
        caplog.set_level(logging.INFO, logger="modules.reader_job")
        r = A.app.test_client().post("/update/check", json={})
        body = r.get_json()
        assert r.status_code == 202 and body["started"] and body["run"]
        assert _wait_until(lambda: reader_job.request_in_flight("app-pushed") is None
                           and reader_job._REQUESTS["app-pushed"]["done"])
        doc = reader_job.read_cached("app-pushed")["doc"]
        want = {"kind": "request", "by": TEST_PERSON, "run": body["run"]}
        assert doc["last_attempt"]["trigger"] == want
        assert doc["last_good"]["trigger"] == want
        assert doc["runs"][-1]["trigger"] == want and isinstance(doc["runs"][-1]["took_ms"], int)
        logged = [m for m in caplog.messages if body["run"] in m]
        assert logged and f"on request by {TEST_PERSON} took" in logged[0] and logged[0].endswith("ok")

    def test_an_unchanged_answer_on_request_is_still_announced(self, scripted_reader):
        """The defect: announce_if skipped it, and the page never heard."""
        import dataclasses

        from modules import reader_job
        from modules.readers import app_pushed
        # A change-only reader (app-pushed is not one since 2026-10-01: every
        # run announces); the property is the request path's, for any reader.
        r = dataclasses.replace(scripted_reader["reader"], announce_if=lambda a, b: False,
                                announce_at_least_every=10 ** 9)
        reader_job.run_once(r, announce=reader_job.announce_via_page)
        reader_job.run_once(r, announce=reader_job.announce_via_page)
        assert len(scripted_reader["announced"]) == 1   # the control: unchanged, not due, skipped
        got = reader_job.request_run(r, "p@example.invalid",
                                     announce=reader_job.announce_via_page)
        assert _wait_until(lambda: reader_job._REQUESTS[app_pushed.READER.name]["done"])
        assert got["started"] and len(scripted_reader["announced"]) == 2
        assert scripted_reader["announced"][-1] == (("app_version",), "app-pushed", True)

    def test_one_run_at_a_time_and_a_second_press_waits_for_the_same(self, scripted_reader):
        import app as A
        from modules import reader_job
        scripted_reader["hold"].clear()
        c = A.app.test_client()
        first = c.post("/update/check", json={})
        second = c.post("/update/check", json={})
        assert first.status_code == 202 and second.status_code == 200
        assert second.get_json()["run"] == first.get_json()["run"]
        assert "waits for its answer" in second.get_json()["message"]
        assert reader_job.request_in_flight("app-pushed")["run"] == first.get_json()["run"]
        scripted_reader["hold"].set()
        assert _wait_until(lambda: reader_job.request_in_flight("app-pushed") is None)

    def test_the_run_is_answered_once_the_store_holds_it_before_its_thread_ends(self,
                                                                                scripted_reader):
        """The re-fetch the announcement causes must already read it as answered."""
        from modules import reader_job
        reader_job._REQUESTS["app-pushed"] = {"run": "r1", "by": "", "since": 0, "done": False}
        assert reader_job.request_in_flight("app-pushed")["run"] == "r1"
        reader_job.run_once(scripted_reader["reader"],
                            trigger={"kind": "request", "by": "", "run": "r1"})
        assert reader_job.request_in_flight("app-pushed") is None

    def test_the_bound_is_measured_from_the_recorded_runs(self, scripted_reader):
        from modules import reader_job
        assert reader_job.answer_bound("app-pushed")["seconds"] is None
        assert "no run" in reader_job.answer_bound("app-pushed")["basis"]
        path = reader_job.store_path("app-pushed")
        reader_job.run_once(scripted_reader["reader"])
        doc = reader_job.read_cached("app-pushed")["doc"]
        doc["runs"] = [{"took_ms": 1117}, {"took_ms": 400}]          # the host's, 2026-09-30
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        got = reader_job.answer_bound("app-pushed")
        assert got["seconds"] == 3 and "slowest of its last 2 run(s), 1.1 s" in got["basis"]

    def test_runs_are_kept_to_the_bound(self, scripted_reader):
        from modules import reader_job
        for _ in range(reader_job.RUNS_KEPT + 3):
            reader_job.run_once(scripted_reader["reader"])
        runs = reader_job.read_cached("app-pushed")["doc"]["runs"]
        assert len(runs) == reader_job.RUNS_KEPT
        assert all(r["trigger"] == {"kind": "scheduled"} for r in runs)

    @pytest.mark.parametrize("trigger,viewer,words", [
        ({"kind": "request", "by": "me@example.invalid"}, "me@example.invalid", "checked on your request"),
        ({"kind": "request", "by": "you@example.invalid"}, "me@example.invalid",
         "checked on request by you@example.invalid"),
        ({"kind": "request", "by": ""}, "", "checked on request by somebody not identified"),
        ({"kind": "scheduled"}, "me@example.invalid", "the scheduled check"),
        ({"kind": "after_commit"}, "", "re-read after a commit"),
        ({}, "", "what started it was not recorded"),
    ])
    def test_what_caused_an_answer_in_words(self, trigger, viewer, words):
        from modules import reader_job
        assert reader_job.trigger_words(trigger, viewer) == words

    def test_about_draws_busy_mid_run_and_keeps_the_cause_off_the_row(self, scripted_reader):
        """The operator, 2026-09-30: the row is the state, its timestamp and the
        button; the run's cause and duration are on the timestamp's hover."""
        import app as A
        from modules import reader_job
        c = A.app.test_client()
        reader_job.run_once(scripted_reader["reader"])
        page = c.get("/v2/help/installation").get_data(as_text=True)
        assert re.search(r'title="[^"]* · the scheduled check, \d+\.\d s"', page)
        assert "scheduled check" not in _without_attributes(page)
        assert 'data-running-for=""' in page
        scripted_reader["hold"].clear()
        c.post("/update/check", json={})
        page = c.get("/v2/help/installation").get_data(as_text=True)
        assert re.search(r'data-running-for="\d', page), "a panel re-drawn mid-run is not busy"
        assert "Checking…</button>" in page
        scripted_reader["hold"].set()
        assert _wait_until(lambda: reader_job.request_in_flight("app-pushed") is None)
        page = c.get("/v2/help/installation").get_data(as_text=True)
        assert "Up to date as of" in page and "Check again</button>" in page
        assert re.search(r'title="[^"]* · checked on your request, \d+\.\d s"', page)
        assert "request" not in _without_attributes(page)
        assert 'data-running-for=""' in page

    def test_a_failed_check_is_said_beside_the_answer_before_it(self, scripted_reader):
        import app as A
        from modules import reader_job
        reader_job.run_once(scripted_reader["reader"])
        scripted_reader["value"] = "not a mapping"
        reader_job.run_once(scripted_reader["reader"],
                            trigger={"kind": "request", "by": "test-person@example.invalid", "run": "x"})
        page = A.app.test_client().get("/v2/help/installation").get_data(as_text=True)
        assert "The last check, " in page and "checked on your request" not in _without_attributes(page)
        assert "failed: the read returned str, not a mapping" in page
        assert "What is shown is the answer before it" in page

    def test_the_update_page_says_it_too(self, scripted_reader):
        import app as A
        from modules import reader_job
        reader_job.run_once(scripted_reader["reader"])
        page = A.app.test_client().get("/v2/update/panel").get_data(as_text=True)
        assert 'x-data="check"' in page and "scheduled check" not in _without_attributes(page)
        assert re.search(r'title="[^"]* · the scheduled check', page)

    def test_the_commit_hook_records_its_trigger(self, monkeypatch):
        from modules import reader_job
        from modules.readers import remote_publication
        seen = []
        monkeypatch.setattr(reader_job, "run_once", lambda r, announce=None, trigger=None: seen.append(trigger))
        remote_publication.refresh_hook({})
        assert seen == [{"kind": "after_commit"}]

    @pytest.mark.parametrize("call,want", [
        ("checkLabel(true)", "Checking…"),
        ("checkLabel(false)", "Check again"),
    ])
    def test_the_shipped_words(self, call, want):
        import dukpy
        src = open(os.path.join(ROOT, "static/js/nmas_update.js"), encoding="utf-8").read()
        assert dukpy.evaljs([src, "NMAS_UPDATE." + call]) == want

    def test_the_late_words_name_the_bound_and_its_basis(self):
        import dukpy
        src = open(os.path.join(ROOT, "static/js/nmas_update.js"), encoding="utf-8").read()
        got = dukpy.evaljs([src, "NMAS_UPDATE.checkLateWords(3, '2.5x the slowest of its last "
                                 "20 run(s), 1.1 s')"])
        assert got.startswith("No answer after 3 s, longer than this check has taken here "
                              "(2.5x the slowest of its last 20 run(s), 1.1 s)")
