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
         reachable=True, restart_fails=False, ready=(True, "test: sudo authorised"),
         wait=False, host_check=None):
    mod = _script()
    calls = []

    def get(path):
        calls.append(path)
        if not reachable:
            return 0, None, "URLError: timed out"
        if "head_sha=" in path:
            sha = path.split("head_sha=")[1].split("&")[0]
            # A SHA listed as `passed` answers its own query with a passing
            # run: the gate asks about each ancestor by SHA (2026-09-28).
            runs = runs_by_sha.get(sha, _run_entry(sha) if sha in passed else [])
            # A function of how many times CI was asked: a run that MOVES
            # while --wait follows it.
            runs = runs(sum(1 for c in calls if "head_sha=" in c)) if callable(runs) else runs
            return 200, {"workflow_runs": runs}, ""
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

    code = mod.main(["--repo", world.host] + (["--offline"] if offline else [])
                    + (["--wait"] if wait else []),
                    get=get, run=lambda *a, **k: Out(), restart=restart,
                    health=fake_health, clock=clock, sleep=sleep, unit=unit,
                    ready=lambda: ready, host_check=host_check or (lambda repo: None))
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
        assert code == 7 and _head(world) == world.base      # PENDING (C124)

    def test_wait_follows_a_running_run_and_deploys_when_it_passes(self, world, capsys):
        """--wait (the operator, 2026-09-28): 35 "still running" refusals
        across 19 waits was a retry loop. The tool follows the run instead,
        printing what it is doing, and the gate is the same gate."""
        sha = world.advance({"app.py": "v = 2\n"})
        moving = {sha: lambda asked: (_run_entry(sha) if asked >= 4
                                      else _run_entry(sha, None, "in_progress"))}
        code, restarted, calls = _run(world, moving, wait=True)
        out = capsys.readouterr().out
        assert code == 0 and _head(world) == sha and restarted
        assert sum(1 for c in calls if "head_sha=" in c) == 4
        assert out.count("waiting ") == 2, out
        assert "typically ~200 s" in out and "of at most 600 s" in out
        assert "waited " in out and "CI passed" in out

    def test_wait_stops_at_the_bound_and_says_so(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, restarted, _ = _run(world, {sha: _run_entry(sha, None, "in_progress")},
                                  wait=True)
        err = capsys.readouterr().err
        assert code == 7 and _head(world) == world.base and not restarted
        assert "still PENDING after waiting" in err and "the bound, 600 s" in err

    def test_wait_ends_at_once_on_a_failure(self, world, capsys):
        """The gate is unchanged: a run that fails while followed refuses."""
        sha = world.advance({"app.py": "v = 2\n"})
        failing = {sha: lambda asked: (_run_entry(sha, "failure") if asked >= 2
                                       else _run_entry(sha, None, "in_progress"))}
        code, restarted, calls = _run(world, failing, wait=True)
        assert code == 1 and _head(world) == world.base and not restarted
        assert sum(1 for c in calls if "head_sha=" in c) == 2

    def test_without_wait_a_running_run_still_refuses_at_once(self, world):
        """The control: --wait is opt-in, and the default is unchanged."""
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, calls = _run(world, {sha: _run_entry(sha, None, "in_progress")})
        assert code == 7 and sum(1 for c in calls if "head_sha=" in c) == 1

    def test_a_cancelled_run_is_not_a_pass(self, world):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha, "cancelled")})
        assert code == 8 and _head(world) == world.base      # CANCELLED (C124)

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


class TestTheWalkAsksEachAncestor:
    """The operator's finding, 2026-09-28: 4ec7ffb (docs only) on 6991b32
    (#148 passed) was refused with "no passing ancestor within 100 commits".
    The old walk tested ancestors against ONE filtered listing of passing
    runs, and that message described a search it never made. Each ancestor
    is now asked about by SHA, named with what was found, and the walk stops
    at the first commit that HAS runs."""

    def test_the_operators_shape_deploys_and_names_what_it_asked(self, world, capsys):
        """green, docs, green, docs: the target's parent passed."""
        world.advance({"app.py": "v = 2\n"}, "e986e66: green")
        world.advance({"docs/NOTE.md": "x\n"}, "6fc7b59: docs")
        green = world.advance({"app.py": "v = 3\n"}, "6991b32: green")
        sha = world.advance({"docs/OPEN.md": "y\n"}, "4ec7ffb: docs")
        code, _, calls = _run(world, {}, passed=[green, world.base])
        out = capsys.readouterr().out
        assert code == 0 and _head(world) == sha, out
        assert f"Asked: {sha[:10]}: no run; {green[:10]}: run #? passed." in out
        assert not any("status=success" in c for c in calls), "the filtered listing is not asked"

    def test_two_docs_only_commits_in_a_row_deploy(self, world, capsys):
        green = world.advance({"app.py": "v = 2\n"}, "green")
        d1 = world.advance({"docs/A.md": "a\n"}, "docs 1")
        d2 = world.advance({"docs/B.md": "b\n"}, "docs 2")
        code, _, _ = _run(world, {}, passed=[green])
        out = capsys.readouterr().out
        assert code == 0 and _head(world) == d2, out
        assert f"{d2[:10]}: no run; {d1[:10]}: no run; {green[:10]}: run #? passed" in out

    def test_a_failed_code_commit_stops_the_walk_before_an_older_pass(self, world, capsys):
        """The dangerous direction: never walk past a failure to an older pass."""
        world.advance({"app.py": "v = 2\n"}, "green")
        bad = world.advance({"app.py": "v = 666\n"}, "failing code")
        world.advance({"docs/X.md": "x\n"}, "docs on top")
        code, _, calls = _run(world, {bad: _run_entry(bad, "failure")},
                              passed=[world.base])
        err = capsys.readouterr().err
        # A definite FAILURE, never "could not ask" (the operator, 2026-10-01: #241
        # failed, and the docs-only commit on top read could_not_ask).
        assert code == 1 and _head(world) == world.base
        assert err.startswith("FAILED:") or "FAILED:" in err
        assert f"the nearest ancestor with one, {bad[:10]}, failed: run #? concluded failure" in err
        assert not any(world.base in c for c in calls), "it never asked past the failure"

    def test_a_cancelled_commit_is_no_verdict_and_the_walk_goes_on(self, world, capsys):
        """A cancelled run is "no verdict, keep walking", never "could not ask".
        A CODE commit passed over that way still refuses, on its change."""
        bad = world.advance({"app.py": "v = 2\n"}, "superseded")
        world.advance({"docs/X.md": "x\n"}, "docs")
        code, _, _ = _run(world, {bad: _run_entry(bad, "cancelled")}, passed=[world.base])
        err = capsys.readouterr().err
        assert code == 2 and "cancelled (no verdict: keep walking)" in err
        assert "changes more than ignored paths" in err

    def test_two_cancelled_then_a_failure_is_the_failure(self, world, capsys):
        """The operator's exact case: 5e394aa (docs) on b14b470 (#241 failed) on
        6a5689f and cf4bfda (cancelled). The walk meets the failure first."""
        c1 = world.advance({"app.py": "v = 2\n"}, "cancelled one")
        c2 = world.advance({"app.py": "v = 3\n"}, "cancelled two")
        bad = world.advance({"app.py": "v = 4\n"}, "failed")
        world.advance({"docs/X.md": "x\n"}, "docs")
        code, _, _ = _run(world, {c1: _run_entry(c1, "cancelled"), c2: _run_entry(c2, "cancelled"),
                                  bad: _run_entry(bad, "failure")}, passed=[world.base])
        err = capsys.readouterr().err
        assert code == 1 and f"{bad[:10]}, failed" in err

    def test_a_cancelled_docs_commit_walks_on_to_a_pass(self, world, capsys):
        """A docs commit whose own run was cancelled is no verdict: the walk
        reaches the pass beneath, and the docs-only change deploys."""
        d1 = world.advance({"docs/A.md": "a\n"}, "docs, run cancelled")
        world.advance({"docs/B.md": "b\n"}, "docs on top")
        code, _, _ = _run(world, {d1: _run_entry(d1, "cancelled")}, passed=[world.base])
        assert code == 0, capsys.readouterr().err

    def test_a_running_code_commit_is_pending_so_wait_can_follow_it(self, world, capsys):
        running = world.advance({"app.py": "v = 2\n"}, "still running")
        world.advance({"docs/X.md": "x\n"}, "docs")
        code, _, _ = _run(world, {running: _run_entry(running, None, "in_progress")})
        assert code == 7 and "is still running" in capsys.readouterr().err

    def test_a_code_commit_with_no_run_is_passed_over_and_its_change_refuses(self, world, capsys):
        """No run is only expected for ignored paths: the diff from the pass
        names the code change the walk passed over."""
        world.advance({"app.py": "v = 2\n"}, "code, no run")
        world.advance({"docs/X.md": "x\n"}, "docs")
        code, _, _ = _run(world, {}, passed=[world.base])
        err = capsys.readouterr().err
        assert code == 2 and "app.py" in err and "Asked:" in err

    def test_past_the_bound_it_refuses_naming_every_commit_it_asked(self, world, capsys):
        mod = _script()
        for n in range(mod.WALK_BOUND + 1):
            world.advance({f"docs/N{n}.md": "x\n"}, f"docs {n}")
        code, _, calls = _run(world, {}, passed=[world.base])
        err = capsys.readouterr().err
        asked = sum(1 for c in calls if "head_sha=" in c)
        assert code == 2 and asked == mod.WALK_BOUND + 1
        assert f"none of the {mod.WALK_BOUND + 1} commit(s) asked about has one" in err
        assert err.count(": no run") == mod.WALK_BOUND + 1

    def test_the_bound_comes_from_the_measured_streak(self):
        assert _script().WALK_BOUND == 10       # 2.5x the longest streak, 4 (2026-09-28)


class TestNothingChanged:
    """The operator's finding, 2026-09-28: an empty commit (41a4149, the
    corrected message for 17e9c7d) changes no file, so GitHub starts no run,
    and the gate refused it saying it "changes more than ignored paths: []".
    The empty case had fallen out of a rule written for the non-empty one."""

    def _empty_commit(self, world, message="corrected message"):
        _git(world.dev, "commit", "-q", "--allow-empty", "-m", message)
        _git(world.dev, "push", "-q", "origin", "main")
        return _git(world.dev, "rev-parse", "HEAD")

    def test_an_empty_commit_on_a_green_one_deploys_by_tree_identity(self, world, capsys):
        green = world.advance({"app.py": "v = 2\n"}, "green")
        sha = self._empty_commit(world)
        code, _, _ = _run(world, {}, passed=[green])
        out = capsys.readouterr().out
        assert code == 0 and _head(world) == sha, out
        assert "tree is IDENTICAL" in out and green[:10] in out

    def test_an_empty_commit_on_a_commit_ci_never_saw_is_refused(self, world, capsys):
        """The dangerous direction: an unchanged tree proves nothing unless
        the tree it matches is one CI PASSED."""
        world.advance({"app.py": "v = 2\n"}, "never verified")
        self._empty_commit(world)
        code, _, _ = _run(world, {}, passed=[world.base])
        assert code == 2 and _head(world) == world.base
        assert "app.py" in capsys.readouterr().err

    def test_a_revert_to_a_green_tree_is_the_same_code_and_deploys(self, world):
        """Tree identity, not an empty diff of one commit: a change and its
        revert leave the green tree, which is what CI verified."""
        green = world.advance({"app.py": "v = 2\n"}, "green")
        world.advance({"app.py": "v = 3\n"}, "change")
        sha = world.advance({"app.py": "v = 2\n"}, "revert")
        code, _, _ = _run(world, {}, passed=[green])
        assert code == 0 and _head(world) == sha

    def test_the_gate_decides_the_empty_case_before_the_ignore_rule(self):
        src = open(os.path.join(ROOT, "scripts", "nmas-deploy")).read()
        gate = src[src.index("# No run for the target."):]
        assert gate.index("^{{tree}}") < gate.index("only_ignored(changed")


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

    def test_a_timeout_names_what_was_running(self, world):
        """nmas-test's bound firing is not "1 failed": the report of what each
        process was running is on stderr, and the verdict carries it."""
        sha = world.advance({"app.py": "v = 2\n", "scripts/nmas-test": "#!/bin/sh\n"})
        _fetch_from_real_origin(world)
        _git(world.host, "fetch", "-q", "origin")

        def spy(argv, cwd=None, **_kw):
            class Out:
                returncode = 124
                stdout = "nmas-test: network: CONFINED (x)\n...."
                stderr = ("nmas-test: TIMED OUT after 300 s (NMAS_TEST_TIMEOUT). Running when "
                          "it stopped:\n  gw3: tests/test_x.py::test_hangs (started 290 s "
                          "before the report)\n--- stacks of gw3 at the SIGTERM ---\n")
            return Out()
        code, message = _script().offline_verdict(world.host, sha, run=spy)
        assert code == 3
        assert "TIMED OUT" in message and "gw3: tests/test_x.py::test_hangs" in message
        assert "FAILED" not in message

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
        assert "ignored_patterns(repo, base)" in src   # the GREEN base the walk found
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


class TestTheRunnerVersionMatchesCI:
    """C45: --offline runs in parallel only with the pytest-xdist the target
    pins, the version CI runs; anything else is serial and says why."""

    @staticmethod
    def _tree(tmp_path, pin="3.8.0"):
        (tmp_path / "requirements-test.txt").write_text(f"pytest-xdist=={pin}\nexecnet==2.1.2\n")
        return str(tmp_path)

    def _with(self, monkeypatch, version):
        import importlib.metadata as md

        def fake(name):
            if name != "pytest-xdist" or version is None:
                raise md.PackageNotFoundError(name)
            return version
        monkeypatch.setattr(md, "version", fake)

    def test_the_pinned_version_runs_in_parallel(self, tmp_path, monkeypatch):
        self._with(monkeypatch, "3.8.0")
        ok, how = _script().parallel_available(self._tree(tmp_path))
        assert ok and "in parallel" in how and "3.8.0" in how

    def test_another_version_runs_serially_naming_both(self, tmp_path, monkeypatch):
        self._with(monkeypatch, "3.4.0")
        ok, how = _script().parallel_available(self._tree(tmp_path))
        assert not ok and "3.4.0" in how and "3.8.0" in how and how.startswith("serially")

    def test_not_installed_runs_serially(self, tmp_path, monkeypatch):
        self._with(monkeypatch, None)
        ok, how = _script().parallel_available(self._tree(tmp_path))
        assert not ok and "not installed" in how


def test_a_refusal_ends_in_one_full_stop(world):
    sha = world.advance({"app.py": "v = 2\n", "scripts/nmas-test": "#!/bin/sh\n"})
    _fetch_from_real_origin(world)
    _git(world.host, "fetch", "-q", "origin")

    def spy(argv, cwd=None, **_kw):
        class Out:
            returncode = 1
            stdout = "nmas-test: network: NOT CONFINED: no namespace (x). Processes CAN reach.\n1 failed"
        return Out()
    _, message = _script().offline_verdict(world.host, sha, run=spy)
    assert ".." not in message and message.endswith(". Refused."), message


class TestItDoesNotStartWhatItCannotFinish:
    """The operator, 2026-09-27: over SSH with no terminal, nmas-deploy moved
    the checkout to 413f90b and then failed at sudo's password prompt, so the
    service ran 912e3f1 against the new checkout, and the exit code told
    nobody. It now refuses BEFORE the checkout moves, and a failure after the
    move leads with one line saying what the state is and what to run."""

    def test_no_restart_possible_means_the_checkout_does_not_move(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        before = _head(world)
        code, restarted, _ = _run(world, {sha: _run_entry(sha)},
                                  ready=(False, "sudo needs a password and there is no terminal"))
        err = capsys.readouterr().err
        assert code == 6 and restarted == []
        assert _head(world) == before, "the checkout moved though it could not restart"
        assert err.startswith("NOT DEPLOYED") and "was NOT moved" in err

    def test_a_failed_restart_leads_with_the_mixed_version(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha)}, restart_fails=True, health="stale")
        first = capsys.readouterr().err.splitlines()[0]
        assert code == 5
        assert first.startswith(f"MIXED VERSION: checkout at {sha[:10]}, service running "
                                f"{world.base[:10]}")
        assert "sudo systemctl restart flask-app.service" in first

    def test_the_control_a_restart_that_worked_names_no_mixed_version(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha)})
        out = capsys.readouterr()
        assert code == 0 and "MIXED" not in out.out + out.err


class TestCanRestart:
    def _runner(self, results):
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            return type("R", (), {"returncode": results.get(tuple(cmd[:2]), 1)})()
        return run, calls

    def test_cached_sudo_passes_without_asking(self):
        mod = _script()
        run, calls = self._runner({("sudo", "-n"): 0})
        assert mod.can_restart(run=run, isatty=lambda: False)[0] is True
        assert calls == [["sudo", "-n", "true"]]

    def test_no_terminal_and_no_cache_refuses_and_says_why(self):
        mod = _script()
        run, calls = self._runner({})
        ok, why = mod.can_restart(run=run, isatty=lambda: False)
        assert ok is False and "no terminal" in why
        assert ["sudo", "-v"] not in calls, "it must not prompt with no terminal"

    def test_a_terminal_asks_for_the_password_before_anything_moves(self):
        mod = _script()
        run, calls = self._runner({("sudo", "-v"): 0})
        assert mod.can_restart(run=run, isatty=lambda: True)[0] is True
        assert calls[-1] == ["sudo", "-v"]



def _runs(*spec):
    """(run_number, conclusion, status) -> run dicts, all created in ONE
    second, as d7efb9d's #92 and #93 were."""
    return [{"run_number": n, "run_attempt": 1, "id": 36367580000 + n,
             "status": status, "conclusion": c, "created_at": "2026-09-28T01:51:33Z",
             "path": ".github/workflows/ci.yml",
             "html_url": f"https://github.com/owner/repo/actions/runs/{n}"}
            for n, c, status in spec]


class TestTheVerdictIsOfTheSetOfRuns:
    """C124: the gate read a CANCELLED run as the verdict for a commit that
    PASSED, because both runs were created in the same second and `max` by
    `created_at` took the first in the API's list. It caused the operator's
    first bypass of the gate (C44)."""

    def test_d7efb9d_exactly_a_cancelled_run_beside_a_pass_is_a_pass(self):
        mod = _script()
        state, run, _ = mod.verdict_of_runs(_runs((92, "cancelled", "completed"),
                                                  (93, "success", "completed")))
        assert state == "PASSED" and run["run_number"] == 93

    def test_a_later_re_run_that_failed_refuses_the_dangerous_direction(self):
        """The same selection that refused a good commit would ACCEPT one
        whose later re-run failed after an earlier pass. List order must not
        decide: the failure is listed LAST and FIRST in turn."""
        mod = _script()
        for order in ((1, 2), (2, 1)):
            runs = _runs((10, "success", "completed"), (11, "failure", "completed"))
            runs = [runs[i - 1] for i in order]
            state, run, _ = mod.verdict_of_runs(runs)
            assert state == "FAILED" and run["run_number"] == 11, order

    def test_a_later_pass_after_a_failure_passes(self):
        mod = _script()
        state, _run, _ = mod.verdict_of_runs(_runs((10, "failure", "completed"),
                                                   (11, "success", "completed")))
        assert state == "PASSED"

    def test_a_run_in_progress_is_pending_whatever_an_earlier_one_said(self):
        mod = _script()
        state, _run, _ = mod.verdict_of_runs(_runs((10, "success", "completed"),
                                                   (11, None, "in_progress")))
        assert state == "PENDING"

    def test_only_cancelled_runs_are_cancelled_not_failed(self):
        mod = _script()
        state, _run, _ = mod.verdict_of_runs(_runs((10, "cancelled", "completed"),
                                                   (11, "cancelled", "completed")))
        assert state == "CANCELLED"

    def test_through_the_gate_the_exact_host_case_deploys(self, world):
        sha = _git(world.origin, "rev-parse", "HEAD")
        code, _, _ = _run(world, {sha: [dict(r, head_sha=sha) for r in
                                        _runs((92, "cancelled", "completed"),
                                              (93, "success", "completed"))]})
        assert code == 0 and _head(world) == sha

    def test_the_three_refusals_say_different_things(self):
        mod = _script()

        def say(*spec):
            runs = [dict(r, head_sha="a" * 40) for r in _runs(*spec)]
            return mod.ci_verdict("/nonexistent", "a" * 40,
                                  get=lambda path: (200, {"workflow_runs": runs}, ""))
        original = mod.git
        mod.git = lambda repo, *a, check=True: "github-nmas:owner/repo.git"
        try:
            failed = say((1, "failure", "completed"))
            pending = say((1, None, "queued"))
            cancelled = say((1, "cancelled", "completed"))
        finally:
            mod.git = original
        assert failed[0] == 1 and failed[1].startswith("FAILED") and "Do not deploy" in failed[1]
        assert pending[0] == 7 and pending[1].startswith("PENDING") and "Wait" in pending[1]
        assert cancelled[0] == 8 and cancelled[1].startswith("CANCELLED")
        assert "newer commit" in cancelled[1]


FAILING_CHECK = (2, "updater: cannot_run: the updater CANNOT RUN: runuser: gone. It began when "
                    "this release started running\n\nRe-install the updater's root-owned copies "
                    "from this release, on the host, in this checkout as the service user:\n"
                    "    cd /srv/checkout\n    sudo systemctl daemon-reload")


class TestTheHostStepsAreSaidLast:
    """The operator, 2026-09-30: 08dbee5 needed the updater re-installed, the
    terminal deploy said nothing, and the updater stayed broken until job
    health caught it. Every deploy now ends with each `Host-Step:` of the
    commits it deployed, checked where it can be, and the updater's own check."""

    def _last_block(self, capsys):
        out = capsys.readouterr().out
        return out[out.rindex("\n\n") + 2:] if "\n\n" in out else ""

    def test_each_step_is_printed_last_and_an_uncheckable_one_says_so(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"},
                            "change\n\nHost-Step: install python3-foo on the host")
        code, _, _ = _run(world, {sha: _run_entry(sha)})
        block = self._last_block(capsys)
        assert code == 0 and block.startswith("HOST STEPS in the commits just deployed (1)")
        assert f"1. {sha[:10]} (BEFORE the update): install python3-foo on the host" in block
        assert "Not checkable from here: confirm it is done by hand." in block

    def test_an_updater_step_still_needed_prints_the_check_and_its_commands(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"}, "change\n\nHost-Step: re-install the "
                                                   "updater's root-owned copies from this release")
        code, _, _ = _run(world, {sha: _run_entry(sha)}, host_check=lambda repo: FAILING_CHECK)
        block = self._last_block(capsys)
        assert code == 0 and "STILL NEEDED. The updater's check says:" in block
        assert block.rstrip().endswith("sudo systemctl daemon-reload")

    def test_an_updater_step_done_says_done(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"}, "change\n\nHost-Step: re-install the updater")
        _run(world, {sha: _run_entry(sha)}, host_check=lambda repo: (0, "updater: ok"))
        assert "Done: nmas-update-check reads ok." in self._last_block(capsys)

    def test_an_earlier_releases_step_is_caught_on_a_later_deploy(self, world, capsys):
        """The operator's af8630a: deployed after 08dbee5 with its step undone."""
        sha = world.advance({"app.py": "v = 2\n"})
        _run(world, {sha: _run_entry(sha)}, host_check=lambda repo: FAILING_CHECK)
        block = self._last_block(capsys)
        assert block.startswith("HOST STEP OUTSTANDING from an earlier release")
        assert "CANNOT RUN" in block

    def test_nothing_to_say_says_nothing(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        _run(world, {sha: _run_entry(sha)}, host_check=lambda repo: (0, "updater: ok"))
        assert "HOST STEP" not in capsys.readouterr().out

    def test_a_refusal_before_anything_moved_lists_no_steps(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"}, "change\n\nHost-Step: install python3-foo")
        code, _, _ = _run(world, {sha: _run_entry(sha, "failure")},
                          host_check=lambda repo: FAILING_CHECK)
        assert code == 1 and "HOST STEP" not in capsys.readouterr().out

    def test_the_updater_check_asks_only_where_an_updater_is_installed(self, tmp_path):
        mod = _script()
        mod.INSTALLED_UPDATER = str(tmp_path / "absent")
        assert mod.updater_check(str(tmp_path), run=lambda *a, **k: 1 / 0) is None
