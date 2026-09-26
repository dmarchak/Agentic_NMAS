"""P.4 step 4: nmas-deploy moves the host only to a commit CI passed.

Driven through `main()` against a real bare "origin" and a clone, with the
GitHub API, the restart and the health check injected. HEAD is asserted
UNMOVED on every refusal: a refusal that had already fast-forwarded would be
the defect it exists to prevent.
"""

import importlib.machinery
import importlib.util
import json
import os
import re
import stat
import subprocess
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CI_YML = textwrap.dedent("""\
    name: ci
    on:
      push:
        paths-ignore: ["docs/**", "**/*.md"]
    jobs: {}
    """)


def _script():
    path = os.path.join(ROOT, "scripts", "nmas-deploy")
    loader = importlib.machinery.SourceFileLoader("nmas_deploy", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


def _commit(repo, files, message):
    for rel, text in files.items():
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def world(tmp_path):
    """origin (bare) <- dev (pushes) ; host (the deployed clone)."""
    origin, dev, host = (str(tmp_path / n) for n in ("origin.git", "dev", "host"))
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True)
    subprocess.run(["git", "clone", "-q", origin, dev], check=True, capture_output=True)
    _git(dev, "checkout", "-q", "-b", "main")
    base = _commit(dev, {".github/workflows/ci.yml": CI_YML, "app.py": "v = 1\n"}, "base")
    _git(dev, "push", "-q", "origin", "main")
    subprocess.run(["git", "clone", "-q", "-b", "main", origin, host], check=True, capture_output=True)
    _git(host, "remote", "set-url", "origin", "github-nmas:owner/repo.git")
    _git(host, "config", "remote.origin.pushurl", origin)
    os.makedirs(os.path.join(host, "data"))

    class W:
        pass
    w = W()
    w.origin, w.dev, w.host, w.base = origin, dev, host, base

    def advance(files, message="change"):
        sha = _commit(dev, files, message)
        _git(dev, "push", "-q", "origin", "main")
        return sha
    w.advance = advance
    return w


def _fetch_from_real_origin(world):
    """The host's origin URL is a GitHub-shaped alias (for the slug); fetch
    through the real bare repository the test built."""
    _git(world.host, "config", "remote.origin.url", world.origin)


def _run(world, runs_by_sha, passed=(), offline=False, suite_rc=0, health="fresh",
         reachable=True, restart_fails=False):
    mod = _script()
    calls = []

    def get(path):
        calls.append(path)
        if not reachable:
            return 0, None, "URLError: timed out"
        if "head_sha=" in path:
            sha = path.split("head_sha=")[1].split("&")[0]
            return 200, {"workflow_runs": runs_by_sha.get(sha, [])}, ""
        return 200, {"workflow_runs": [{"head_sha": s, "path": ".github/workflows/ci.yml",
                                        "status": "completed", "conclusion": "success"}
                                       for s in passed]}, ""

    # slug_of reads the URL; the fetch needs the real path. Give git both.
    real_remote = mod.git

    def git(repo, *args, check=True):
        if args[:2] == ("remote", "get-url"):
            return "github-nmas:owner/repo.git"
        return real_remote(repo, *args, check=check)
    mod.git = git
    _fetch_from_real_origin(world)

    class Out:
        returncode = suite_rc
        stdout = "3942 passed" if suite_rc == 0 else "1 failed, 3941 passed"

    now = [1_800_000_000.0]
    def clock():
        now[0] += 0.25
        return now[0]
    def sleep(seconds):
        now[0] += seconds
    restarted = []

    def restart():
        if restart_fails:
            raise subprocess.CalledProcessError(1, "systemctl", stderr="Unit not found")
        restarted.append(now[0])

    def unit():
        """systemd: MainPID 100 before the restart, 200 after, unless the
        restart never happened (`unchanged_pid`)."""
        pid = 200 if (restarted and health != "unchanged_pid") else 100
        return {"MainPID": pid, "start": "Sat 2026-09-26 20:14:42.123456 UTC"}

    def fake_health():
        """What /health answers. `fresh`: the target, from the new pid, with
        an app start time 0.9 s BEFORE the restart was issued (the /proc bias
        the operator measured: identity must not depend on it). `stale`: the
        OLD commit. `foreign_pid`: answered by a process that is not the
        service's MainPID. `missing`: no /health."""
        running = _git(world.host, "rev-parse", "HEAD")
        early = mod.iso_ms((restarted[-1] if restarted else now[0]) - 0.9)
        if health == "missing":
            return 404, None
        if health == "stale":
            return 200, {"commit": world.base, "started_at": early, "pid": unit()["MainPID"]}
        if health == "foreign_pid":
            return 200, {"commit": running, "started_at": early, "pid": 999}
        return 200, {"commit": running, "started_at": early, "pid": unit()["MainPID"]}

    code = mod.main(["--repo", world.host] + (["--offline"] if offline else []),
                    get=get, run=lambda *a, **k: Out(), restart=restart,
                    health=fake_health, clock=clock, sleep=sleep, unit=unit)
    return code, restarted, calls


def _run_entry(sha, conclusion="success", status="completed"):
    return [{"head_sha": sha, "path": ".github/workflows/ci.yml", "status": status,
             "conclusion": conclusion, "created_at": "2026-09-26T00:00:00Z",
             "html_url": f"https://github.com/owner/repo/actions/runs/{sha[:6]}"}]


def _head(world):
    return _git(world.host, "rev-parse", "HEAD")


class TestTheGate:
    def test_a_passing_run_deploys(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, restarted, _ = _run(world, {sha: _run_entry(sha)})
        assert code == 0 and _head(world) == sha and restarted

    def test_a_failed_run_refuses_and_names_it(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, restarted, _ = _run(world, {sha: _run_entry(sha, "failure")})
        err = capsys.readouterr().err
        assert code == 1 and _head(world) == world.base and not restarted
        assert sha[:10] in err and "failure" in err and "actions/runs" in err

    def test_a_running_run_refuses(self, world):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha, None, "in_progress")})
        assert code == 1 and _head(world) == world.base

    def test_a_cancelled_run_is_not_a_pass(self, world):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha, "cancelled")})
        assert code == 1 and _head(world) == world.base

    def test_github_unreachable_is_could_not_ask_and_refuses(self, world, capsys):
        world.advance({"app.py": "v = 2\n"})
        code, restarted, _ = _run(world, {}, reachable=False)
        assert code == 2 and _head(world) == world.base and not restarted
        assert "--offline" in capsys.readouterr().err


class TestNoRunFound:
    """Exit 2, never a pass: the old Jenkins ci_gate's shape, refused."""

    def test_no_run_and_code_changed_is_refused(self, world, capsys):
        world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {}, passed=[world.base])
        assert code == 2 and _head(world) == world.base
        assert "app.py" in capsys.readouterr().err

    def test_no_run_and_no_passing_ancestor_is_refused(self, world):
        world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {}, passed=[])
        assert code == 2 and _head(world) == world.base

    def test_a_docs_only_push_passes_on_its_ancestors_run(self, world, capsys):
        sha = world.advance({"docs/NOTE.md": "x\n", "README.md": "y\n"})
        code, _, _ = _run(world, {}, passed=[world.base])
        assert code == 0 and _head(world) == sha
        assert "paths-ignore" in capsys.readouterr().out


class TestTheIgnoreRuleComesFromAGreenCommit:
    """The operator's question, 2026-09-26: whose paths-ignore decides a
    no-run push? Read at the target, a commit that widens it to '**' produces
    no run and would be called expected."""

    WIDE = CI_YML.replace('["docs/**", "**/*.md"]', '["**"]')

    def test_a_commit_widening_paths_ignore_is_refused(self, world, capsys):
        world.advance({".github/workflows/ci.yml": self.WIDE, "app.py": "v = 2\n"})
        code, _, _ = _run(world, {}, passed=[world.base])
        assert code == 2 and _head(world) == world.base
        assert "app.py" in capsys.readouterr().err

    def test_a_workflow_change_is_never_ignorable(self, world):
        """Even when the GREEN commit's own patterns would ignore it."""
        yml_ignored = CI_YML.replace('["docs/**", "**/*.md"]', '["docs/**", "**/*.md", "**/*.yml"]')
        green = world.advance({".github/workflows/ci.yml": yml_ignored}, "green, ignores yml")
        world.advance({".github/workflows/ci.yml": yml_ignored + "# edited\n"}, "workflow edit")
        code, _, _ = _run(world, {}, passed=[green])
        assert code == 2

    def test_the_floor_a_docs_change_still_passes(self, world):
        yml_ignored = CI_YML.replace('["docs/**", "**/*.md"]', '["docs/**", "**/*.md", "**/*.yml"]')
        green = world.advance({".github/workflows/ci.yml": yml_ignored}, "green")
        sha = world.advance({"docs/x.md": "y\n", "config.yml": "a: 1\n"}, "docs and a yml")
        code, _, _ = _run(world, {}, passed=[green])
        assert code == 0 and _head(world) == sha


class TestOffline:
    def test_a_failing_suite_here_refuses(self, world, capsys):
        world.advance({"app.py": "v = 2\n"})
        code, _, calls = _run(world, {}, offline=True, suite_rc=1)
        assert code == 3 and _head(world) == world.base and calls == []

    def test_the_suite_runs_in_a_checkout_of_the_target(self, world):
        """A tree with no .git failed /health's test on every commit, so
        --offline could never pass (2026-09-26). The suite must see what a
        deploy runs: a git checkout whose HEAD is the target."""
        sha = world.advance({"app.py": "v = 2\n"})
        _fetch_from_real_origin(world)
        _git(world.host, "fetch", "-q", "origin")
        seen = {}

        def spy(argv, cwd=None, **_kw):
            seen["cwd"] = cwd
            seen["head"] = subprocess.run(["git", "-C", cwd, "rev-parse", "HEAD"],
                                          capture_output=True, text=True).stdout.strip()
            seen["app"] = open(os.path.join(cwd, "app.py")).read()

            class Out:
                returncode, stdout = 0, "1 passed"
            return Out()
        code, _ = _script().offline_verdict(world.host, sha, run=spy)
        assert code == 0
        assert seen["head"] == sha, "the suite ran in something that is not a checkout of the target"
        assert seen["app"] == "v = 2\n"
        assert os.path.realpath(seen["cwd"]) != os.path.realpath(world.host)
        assert _head(world) == world.base, "testing the target must not move the host"

    def test_it_runs_the_targets_own_runner_and_reports_its_network_line(self, world):
        """C46: through scripts/nmas-test when the target has it, allowed to
        run unconfined on a machine that cannot confine, and SAYING which."""
        sha = world.advance({"app.py": "v = 2\n", "scripts/nmas-test": "#!/bin/sh\n"})
        _fetch_from_real_origin(world)
        _git(world.host, "fetch", "-q", "origin")
        seen = {}

        def spy(argv, cwd=None, **_kw):
            seen["argv"] = argv

            class Out:
                returncode = 0
                stdout = ("nmas-test: network: NOT CONFINED: no network namespace here (x)\n"
                          "3986 passed")
            return Out()
        code, message = _script().offline_verdict(world.host, sha, run=spy)
        assert code == 0
        assert seen["argv"][0].endswith(os.path.join("scripts", "nmas-test"))
        assert "--allow-unconfined" in seen["argv"]
        assert "network: NOT CONFINED" in message and "3986 passed" in message

    def test_a_target_without_the_runner_is_reported_unconfined(self, world):
        sha = world.advance({"app.py": "v = 2\n"})
        _fetch_from_real_origin(world)
        _git(world.host, "fetch", "-q", "origin")

        def spy(argv, cwd=None, **_kw):
            class Out:
                returncode, stdout = 1, "1 failed"
            return Out()
        code, message = _script().offline_verdict(world.host, sha, run=spy)
        assert code == 3
        assert "NOT CONFINED (the target has no scripts/nmas-test)" in message

    def test_it_says_what_it_will_cost_before_it_runs(self, world, capsys):
        """C45: the forecast is printed BEFORE the suite runs, from this
        machine's own last --offline row, never a constant."""
        with open(os.path.join(world.host, "data", "deploy_audit.jsonl"), "w") as fh:
            fh.write(json.dumps({"gate": "ci", "started_at": "2026-09-26T20:00:00.000Z",
                                 "ended_at": "2026-09-26T20:00:01.000Z"}) + "\n")
            fh.write(json.dumps({"gate": "offline", "started_at": "2026-09-26T21:15:55.343Z",
                                 "ended_at": "2026-09-26T21:21:41.376Z"}) + "\n")
        sha = world.advance({"app.py": "v = 2\n"})
        _fetch_from_real_origin(world)
        _git(world.host, "fetch", "-q", "origin")
        order = []

        def spy(argv, cwd=None, **_kw):
            order.append(("suite", capsys.readouterr().out))

            class Out:
                returncode, stdout = 0, "1 passed"
            return Out()
        _script().offline_verdict(world.host, sha, run=spy)
        (what, printed), = order
        assert "running the FULL suite here" in printed, "not said before the run"
        assert "took 5m46s" in printed and "2026-09-26T21:15:55.343Z" in printed

    def test_with_no_earlier_run_it_says_so_rather_than_guessing(self, world):
        assert "No earlier --offline run is recorded here." in _script().offline_forecast(world.host)

    def test_a_passing_suite_here_deploys_without_asking_github(self, world):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, calls = _run(world, {}, offline=True, suite_rc=0)
        assert code == 0 and _head(world) == sha and calls == []


class TestLocalState:
    def test_local_edits_refuse_before_anything(self, world):
        world.advance({"app.py": "v = 2\n"})
        with open(os.path.join(world.host, "app.py"), "w") as fh:
            fh.write("edited\n")
        code, _, calls = _run(world, {})
        assert code == 4 and calls == []

    def test_a_diverged_host_is_not_forced(self, world):
        _commit(world.host, {"local.txt": "x\n"}, "local commit")
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha)})
        assert code == 4


class TestAfterTheRestart:
    """A 200 from a process that never restarted used to pass (the operator's
    finding, 2026-09-26). Success now means /health reports the TARGET commit
    from a process that started AFTER the restart was issued."""

    def test_a_moved_deploy_says_so_and_names_the_running_process(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha)})
        out = capsys.readouterr().out
        assert code == 0
        assert (f"deployed {world.base[:10]} -> {sha[:10]}, restarted: pid 100 -> 200, "
                f"running {sha[:10]} since") in out

    def test_already_there_is_not_called_deployed(self, world, capsys):
        code, _, _ = _run(world, {world.base: _run_entry(world.base)})
        out = capsys.readouterr().out
        assert code == 0 and f"already at {world.base[:10]}, restarted" in out
        assert "deployed" not in out.split("already at")[1]

    def test_the_old_commit_still_running_is_not_success(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha)}, health="stale")
        err = capsys.readouterr().err
        assert code == 5 and "NOT confirmed running" in err and world.base[:10] in err

    def test_a_start_time_before_the_restart_still_passes_on_identity(self, world):
        """The operator's case: the app's reported start reads up to a second
        early (measured 0.66 s), and a real restart must not false-fail. The
        `fresh` fake reports 0.9 s BEFORE the restart was issued."""
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha)})
        assert code == 0

    def test_an_unchanged_main_pid_is_not_a_restart(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha)}, health="unchanged_pid")
        err = capsys.readouterr().err
        assert code == 5 and "unchanged from 100" in err

    def test_an_answer_from_another_pid_is_not_the_service(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha)}, health="foreign_pid")
        err = capsys.readouterr().err
        assert code == 5 and "pid 999, not the service's new MainPID 200" in err

    def test_no_health_route_is_not_success(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha)}, health="missing")
        assert code == 5 and "/health answered 404" in capsys.readouterr().err

    def test_a_failed_restart_says_not_restarted(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha)}, restart_fails=True)
        err = capsys.readouterr().err
        assert code == 5 and "NOT restarted" in err and "Unit not found" in err


class TestTheRecord:
    def test_every_run_is_one_row_and_owner_only(self, world):
        sha = world.advance({"app.py": "v = 2\n"})
        _run(world, {sha: _run_entry(sha, "failure")})
        _run(world, {sha: _run_entry(sha)})
        path = os.path.join(world.host, "data", "deploy_audit.jsonl")
        rows = [json.loads(l) for l in open(path)]
        assert [r["exit"] for r in rows] == [1, 0]
        assert rows[0]["to"] == sha and rows[0]["gate"] == "ci" and rows[0]["user"]
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        ok = rows[1]
        # run start and end separately, to the millisecond, and what RAN
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", ok["started_at"])
        assert ok["started_at"] < ok["restart_issued_at"] <= ok["ended_at"]
        assert ok["pid_before"] == 100 and ok["pid_after"] == 200 == ok["running_pid"]
        assert ok["running_commit"] == sha and ok["systemd_start"].endswith(".123456 UTC")


class TestIgnoredPaths:
    @pytest.mark.parametrize("path,ignored", [
        ("README.md", True), ("docs/NSOT_PLAN.md", True), ("docs/a/b/c.txt", True),
        ("app.py", False), ("modules/x.md.py", False), ("scripts/nmas-deploy", False)])
    def test_the_workflow_globs(self, path, ignored):
        assert _script().only_ignored([path], ["docs/**", "**/*.md"]) is ignored

    def test_nothing_changed_is_not_only_ignored(self):
        assert _script().only_ignored([], ["docs/**"]) is False

    def test_the_patterns_are_read_from_the_workflow_not_copied(self):
        src = open(os.path.join(ROOT, "scripts", "nmas-deploy")).read()
        assert "ignored_patterns(repo, ancestor)" in src
        assert "ignored_patterns(repo, target)" not in src
        assert '"docs/**"' not in src


class TestTheHealthRoute:
    @pytest.mark.real_identity
    def test_it_reports_the_loaded_commit_and_process_start_ungated(self):
        import app as A
        body = A.app.test_client().get("/health").get_json()
        head = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        assert body["commit"] == head and body["ok"] is True
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", body["started_at"])
        assert body["pid"] == os.getpid()
