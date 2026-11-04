"""Workstream 0 (docs/LOCAL_CI.md): `scripts/nmas-local-ci`, the root-owned wrapper that runs the
repository's own workflow files under act (nektos/act) and records a verdict per commit.

The operator, 2026-11-03: "don't replicate ci.yml in a separate script (two definitions drift).
Use act ... to run ci.yml itself"; "Where a step can't run under act, the verdict names it as not
run. Never a silent skip, never a pass."

**act's log format is CAPTURED** (tests/fixtures/act/, `TestActsCapturedLog`): act 0.2.89's
own `--json -v` log, run on the laptop 2026-11-03 in its self-hosted mode (no container) over
the two probe workflows beside it, a selection of its lines, none rewritten. It settled what
had been recalled: a step skipped by its `if:` is logged only at debug level (so the runner
runs act verbose), a job's own setup is a `stepid` line, and act's times carry the clock's
offset. The other tests' lines are typed in that captured shape (`_line`), to hold the
wrapper's logic case by case. The first host run captures ci.yml's own log
(docs/LOCAL_CI.md, "The first measured run").

What is held:
- **the verdict of an act run, against the workflow it ran:** every step success, passed; a
  step failed, failed naming it; a failure the workflow declares `continue-on-error`, passed; a
  step or a job act reported nothing of, NOT RUN, named, and the verdict incomplete (never
  green); a step act skipped by its `if:`, passed;
- **the real ci.yml:** every job and every step of it must appear in act's log: a full log is
  passed, a log missing one step names it, and a step planted into the workflow is found;
- **a browser test skipped for want of Firefox** is a test not run (the JUnit files act's
  artifact server kept, plain or zipped);
- **the record:** written whole and renamed (no temporary file left, 0644), a record that cannot
  be read is refused rather than overwritten, and `scripts/nmas-deploy`'s `local_verdict` reads
  what this writes (passed, keyed by sha, judged by tree);
- **a run, end to end with act faked:** a real mirror and fresh clone at the sha, act's command
  line (the image pinned, never pulled, offline actions), each step's duration recorded, a
  failing step red naming it and its job's log, act past its bound red, act reporting no job an
  error (no verdict);
- **schedules from the workflows' own crons**, and the quiet window;
- **the self-test** names what the host lacks;
- **the confinement** (the operator's answer 1, a seccomp profile with least privilege): the
  profile is Docker's own default plus one rule letting `unshare` make a user and a network
  namespace and nothing else, act's containers get it and nothing broader, and a default of
  another shape is refused, never guessed at;
- **the job image** (answer 2): a browser test skipped because Firefox could not start is a
  test not run too, and the deep self-test runs both browsers in the image;
- **no limits yet, online** (answers 3 and 4): every record says both;
- **the override is the terminal's** (answer 5): the updater never passes one, and nothing the
  app serves names it;
- **the workflows under act:** every step that changes the host kernel is skipped under act,
  saying why in its own env.
"""
import ast
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import zipfile

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(rel, name):
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def LC():
    """Loaded inside a fixture, so on a commit without the script each test errors (red),
    never the file's collection."""
    return _load("scripts/nmas-local-ci", "nmas_local_ci")


@pytest.fixture(scope="module")
def ci_yml():
    with open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _line(job, step_id=None, step=None, result=None, stage="Main", took=None, matrix=None,
          job_result=None, raw=None, at="2026-11-03T10:00:00Z"):
    e = {"level": "info", "time": at, "jobID": job, "job": job, "dryrun": False}
    if matrix:
        e["matrix"] = matrix
    if step_id is not None:
        e.update(stepID=[str(step_id)], step=step or str(step_id), stage=stage)
    if result:
        e["stepResult"] = result
    if took is not None:
        e["executionTime"] = took
    if job_result:
        e["jobResult"] = job_result
    if raw is not None:
        e.update(raw_output=True, msg=raw)
    else:
        e["msg"] = f"{result or 'run'} {step or ''}"
    return json.dumps(e)


WF = {"jobs": {"build": {"steps": [{"uses": "actions/checkout@v4"},
                                   {"name": "Tests", "run": "pytest"},
                                   {"name": "Information", "run": "x", "continue-on-error": True},
                                   {"name": "Only on tags", "if": "x", "run": "y"}]}}}


def _full(results=("success", "success", "success", "skipped"), job_result="success"):
    lines = [_line("build", i, s.get("name") or s.get("uses"), r, took=2_000_000_000)
             for i, (s, r) in enumerate(zip(WF["jobs"]["build"]["steps"], results)) if r]
    return lines + [_line("build", job_result=job_result)]


class TestTheVerdictOfAnActRun:
    def test_every_step_succeeding_or_skipped_by_its_if_is_passed(self, LC):
        v = LC.judge(WF, LC.read_act_log(_full()))
        assert v["state"] == "passed" and not v["failed"] and not v["not_run"], v
        assert [s["duration_s"] for s in v["jobs"][0]["steps"]] == [2.0, 2.0, 2.0, 2.0]

    def test_a_failed_step_is_failed_naming_it(self, LC):
        v = LC.judge(WF, LC.read_act_log(_full(("success", "failure", "success", "skipped"),
                                               "failure")))
        assert v["state"] == "failed" and v["failed"] == [
            {"job": "build", "step": "Tests", "result": "failure"}], v

    def test_a_failure_the_workflow_declares_non_gating_is_passed(self, LC):
        v = LC.judge(WF, LC.read_act_log(_full(("success", "success", "failure", "skipped"))))
        assert v["state"] == "passed", v
        info = v["jobs"][0]["steps"][2]
        assert info["result"] == "failure" and info["non_gating"] is True

    def test_a_step_act_reported_nothing_of_is_not_run_and_never_green(self, LC):
        v = LC.judge(WF, LC.read_act_log(_full(("success", None, "success", "skipped"))))
        assert v["state"] == "incomplete" and not v["failed"], v
        assert v["not_run"] == [{"job": "build", "step": "Tests",
                                 "why": "act's log has no result for this step"}]
        assert v["jobs"][0]["steps"][1]["result"] == "not run"

    def test_a_job_act_reported_nothing_of_is_not_run(self, LC):
        wf = {"jobs": dict(WF["jobs"], coverage={"steps": [{"run": "x"}]})}
        v = LC.judge(wf, LC.read_act_log(_full()))
        assert v["state"] == "incomplete"
        assert {"job": "coverage", "step": "(the whole job)",
                "why": "act's log reports nothing of this job"} in v["not_run"]

    def test_a_post_stage_failure_is_kept_over_its_main_success(self, LC):
        lines = _full() + [_line("build", 0, "actions/checkout@v4", "failure", stage="Post")]
        v = LC.judge(WF, LC.read_act_log(lines))
        assert v["state"] == "failed" and v["failed"][0]["step"] == "Run actions/checkout@v4"

    def test_matrix_runs_are_judged_each_on_their_own(self, LC):
        lines = [_line("build", i, None, "success", matrix={"shard": "a"}) for i in range(4)]
        lines += [_line("build", i, None, "success" if i != 1 else "failure",
                        matrix={"shard": "b"}) for i in range(4)]
        v = LC.judge(WF, LC.read_act_log(lines))
        assert v["state"] == "failed" and v["failed"][0]["job"] == "build (b)", v
        assert [j["name"] for j in v["jobs"]] == ["build (a)", "build (b)"]

    def test_a_step_the_workflow_skips_under_act_is_not_run_unless_it_says_why(self, LC):
        """`if: ${{ !env.ACT }}` is act's documented way to skip a step locally: here it is a
        step not run, named, unless the step's own env says why it need not run."""
        wf = {"jobs": {"build": {"steps": [
            {"name": "Allow a namespace", "if": "${{ !env.ACT }}", "run": "sudo sysctl x"},
            {"name": "Said why", "if": "${{ !env.ACT }}", "run": "y",
             "env": {"NMAS_ACT_NOT_GATING": "the runner gives the namespace itself"}}]}}}
        act = LC.read_act_log([_line("build", 0, "Allow a namespace", "skipped"),
                               _line("build", 1, "Said why", "skipped")])
        v = LC.judge(wf, act)
        assert v["state"] == "incomplete"
        assert v["not_run"] == [{"job": "build", "step": "Allow a namespace",
                                 "why": "the workflow skips it under act, and its env names "
                                        "no NMAS_ACT_NOT_GATING"}]
        said = v["jobs"][0]["steps"][1]
        assert (said["result"], said["non_gating"]) == ("not run (act)", True)
        assert said["why"] == "the runner gives the namespace itself"
        wf["jobs"]["build"]["steps"][0]["env"] = {"NMAS_ACT_NOT_GATING": "a reason"}
        assert LC.judge(wf, act)["state"] == "passed"

    def test_a_line_that_is_not_json_is_counted_never_read(self, LC):
        act = LC.read_act_log(["not json", ""] + _full())
        assert act["bad"] == 1 and LC.judge(WF, act)["state"] == "passed"


def _ci_log(ci_yml, drop=None):
    """An act log reporting every job and every step of ci.yml (the test job as its five
    shards), each a success; *drop* (job, step index) left out."""
    lines = []
    for job_id, jdoc in ci_yml["jobs"].items():
        runs = [{"shard": s} for s in ("browser1", "browser2", "browser3", "a", "b")] \
            if "strategy" in jdoc else [None]
        for m in runs:
            for i, s in enumerate(jdoc.get("steps") or []):
                if (job_id, i) != drop:
                    lines.append(_line(job_id, s.get("id") or i, s.get("name"), "success",
                                       matrix=m))
            lines.append(_line(job_id, job_result="success", matrix=m))
    return lines


class TestTheRealWorkflow:
    """Every job and step of the repository's own ci.yml, as act would report them."""

    def test_every_step_reported_is_passed(self, LC, ci_yml):
        # The floor, measured 2026-11-03: 3 jobs, 31 steps in all.
        assert set(ci_yml["jobs"]) == {"scope", "test", "coverage"}
        assert sum(len(j.get("steps") or []) for j in ci_yml["jobs"].values()) >= 30
        v = LC.judge(ci_yml, LC.read_act_log(_ci_log(ci_yml)))
        assert v["state"] == "passed", v["not_run"][:3]
        assert len(v["jobs"]) == 7

    def test_a_step_missing_from_acts_log_is_named(self, LC, ci_yml):
        i = next(i for i, s in enumerate(ci_yml["jobs"]["test"]["steps"])
                 if (s.get("name") or "").startswith("Tests (R1, R4)"))
        v = LC.judge(ci_yml, LC.read_act_log(_ci_log(ci_yml, drop=("test", i))))
        assert v["state"] == "incomplete"
        assert {(n["job"], n["step"]) for n in v["not_run"]} == {
            (f"test ({s})", ci_yml["jobs"]["test"]["steps"][i]["name"])
            for s in ("a", "b", "browser1", "browser2", "browser3")}

    def test_a_step_planted_in_the_workflow_is_found(self, LC, ci_yml):
        planted = json.loads(json.dumps(ci_yml))
        planted["jobs"]["coverage"]["steps"].append({"name": "A planted step", "run": "true"})
        v = LC.judge(planted, LC.read_act_log(_ci_log(ci_yml)))
        assert v["state"] == "incomplete"
        assert v["not_run"] == [{"job": "coverage", "step": "A planted step",
                                 "why": "act's log has no result for this step"}]


JUNIT = (b'<?xml version="1.0"?><testsuites><testsuite name="pytest">'
         b'<testcase classname="tests.test_swaps_in_a_browser" name="test_swap">'
         b'<skipped message="no firefox on this machine"/></testcase>'
         b'<testcase classname="tests.test_records" name="test_pg">'
         b'<skipped message="the laptop has no libpq"/></testcase>'
         b'<testcase classname="tests.test_x" name="test_ok"/></testsuite></testsuites>')


class TestABrowserTestSkippedIsNotRun:
    def test_a_plain_junit_file(self, LC, tmp_path):
        (tmp_path / "coverage-browser1").mkdir()
        (tmp_path / "coverage-browser1" / "junit-browser1.xml").write_bytes(JUNIT)
        found = LC.junit_env_skips(str(tmp_path))
        assert found == [{"job": "junit-browser1.xml",
                          "step": "tests.test_swaps_in_a_browser::test_swap",
                          "why": "skipped: no firefox on this machine"}]

    def test_a_zipped_artifact(self, LC, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("junit-browser2.xml", JUNIT)
        (tmp_path / "coverage-browser2.zip").write_bytes(buf.getvalue())
        assert [f["step"] for f in LC.junit_env_skips(str(tmp_path))] == [
            "tests.test_swaps_in_a_browser::test_swap"]

    def test_a_firefox_that_could_not_start_is_not_run_too(self, LC, tmp_path):
        """tests/browser.py's `available()` has three reasons, and the third ("Firefox could
        not start in this runner") is the one a job image with a broken Firefox gives."""
        (tmp_path / "junit-browser3.xml").write_bytes(JUNIT.replace(
            b"no firefox on this machine",
            b"Firefox could not start in this runner: Process unexpectedly closed"))
        assert [f["step"] for f in LC.junit_env_skips(str(tmp_path))] == [
            "tests.test_swaps_in_a_browser::test_swap"]

    def test_every_reason_browser_py_gives_is_one_it_counts(self, LC):
        """The reasons are read from tests/browser.py itself, so a fourth added there and not
        here fails. They are `_probe`'s since C2412: `available` adds only the failure where a
        browser is required, never a skip."""
        with open(os.path.join(ROOT, "tests", "browser.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_probe")
        reasons = [c.value for n in ast.walk(fn) if isinstance(n, ast.Tuple)
                   and len(n.elts) == 2 and isinstance(n.elts[0], ast.Constant)
                   and n.elts[0].value is False
                   for c in [n.elts[1]] if isinstance(c, ast.Constant)]
        reasons += [v.value for n in ast.walk(fn) if isinstance(n, ast.JoinedStr)
                    for v in n.values[:1] if isinstance(v, ast.Constant)]
        assert len(reasons) >= 3, reasons
        for why in reasons:
            assert any(rx.search(why) for rx in LC.ENV_SKIPS), why

    def test_it_turns_a_passed_run_incomplete(self, LC, tmp_path):
        (tmp_path / "junit-a.xml").write_bytes(JUNIT)
        v = LC.judge(WF, LC.read_act_log(_full()), LC.junit_env_skips(str(tmp_path)))
        assert v["state"] == "incomplete" and len(v["not_run"]) == 1


def _real(argv, **kw):
    return subprocess.run(argv, **kw)


def _g(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    env = {k: v for k, v in env.items() if not k.startswith("GIT_") or k.startswith("GIT_AUTHOR")
           or k.startswith("GIT_COMMITTER")}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=env, timeout=30).stdout.strip()


MINI = ("name: ci\non: push\njobs:\n  build:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@v4\n      - name: Tests\n        run: pytest\n")


@pytest.fixture
def world(tmp_path):
    """A store with a mirror holding one commit of a small workflow, owned by this test's
    user (root on the host)."""
    dev, store = tmp_path / "dev", tmp_path / "store"
    dev.mkdir()
    store.mkdir(mode=0o755)
    _g(dev, "init", "-q", "-b", "main")
    (dev / ".github" / "workflows").mkdir(parents=True)
    (dev / ".github" / "workflows" / "ci.yml").write_text(MINI)
    _g(dev, "add", "-A")
    _g(dev, "commit", "-q", "-m", "one")
    sha = _g(dev, "rev-parse", "HEAD")
    subprocess.run(["git", "clone", "-q", "--bare", str(dev), str(store / "mirror.git")],
                   check=True, capture_output=True, timeout=30)
    return {"dev": dev, "store": str(store), "sha": sha,
            "tree": _g(dev, "rev-parse", "HEAD^{tree}")}


#: Docker's bridge gateway as the fake docker answers it (an address from 192.0.2.0/24, the
#: documentation range; this lab's real one is not this test's business).
BRIDGE_GW = "192.0.2.1"


def _fake_docker(argv):
    """Docker, faked: no test talks to the machine's real Docker daemon."""
    if argv[1:3] == ["network", "inspect"]:
        return subprocess.CompletedProcess(argv, 0, stdout=BRIDGE_GW + "\n", stderr="")
    return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")


def _fake_act(results, calls, raise_timeout=False):
    def run(argv, **kw):
        if argv[0] == "/usr/bin/docker":
            return _fake_docker(argv)
        if argv[0] != "/usr/local/bin/act":
            return _real(argv, **kw)
        calls.append(argv)
        if raise_timeout:
            raise subprocess.TimeoutExpired(argv, 1)
        out = kw["stdout"]
        for i, (name, r, took) in enumerate(results):
            out.write(_line("build", i, name, r, took=took) + "\n")
            out.write(_line("build", i, name, raw=f"output of {name}") + "\n")
        if results:
            out.write(_line("build", job_result="failure" if "failure" in
                            [r for _n, r, _t in results] else "success") + "\n")
        return subprocess.CompletedProcess(argv, 0 if results else 1)
    return run


PLATFORM = "ubuntu-24.04=example/runner@sha256:" + "a" * 64


class TestARun:
    def test_a_green_run_records_each_step_and_its_duration(self, LC, world):
        calls = []
        t = iter([1000.0, 1700.0])
        rec = LC.run_commit(world["store"], world["sha"], "", "owner/repo", PLATFORM,
                            run=_fake_act([("Run actions/checkout@v4", "success", 1_500_000_000),
                                           ("Tests", "success", 600_000_000_000)], calls),
                            clock=lambda: next(t))
        assert rec["state"] == "passed" and rec["tree"] == world["tree"], rec
        steps = rec["jobs"][0]["steps"]
        assert [(s["name"], s["result"], s["duration_s"]) for s in steps] == [
            ("Run actions/checkout@v4", "success", 1.5), ("Tests", "success", 600.0)]
        assert rec["duration_s"] == 700.0 and rec["started_at"] == "1970-01-01T00:16:40Z"
        argv = calls[0]
        assert argv[:2] == ["/usr/local/bin/act", "push"] and "--pull=false" in argv
        assert argv[argv.index("-P") + 1] == PLATFORM and "--action-offline-mode" in argv
        assert argv[argv.index("-W") + 1] == ".github/workflows/ci.yml" and "--json" in argv
        event = argv[argv.index("-e") + 1]
        assert not os.path.exists(event), "the run's scratch folder is removed"
        log = os.path.join(world["store"], "runs", world["sha"], "build.log")
        assert open(log).read() == "output of Run actions/checkout@v4\noutput of Tests\n"

    def test_a_failing_step_makes_it_red_naming_the_step_and_its_log(self, LC, world):
        rec = LC.run_commit(world["store"], world["sha"], "", "owner/repo", PLATFORM,
                            run=_fake_act([("Run actions/checkout@v4", "success", 1),
                                           ("Tests", "failure", 1)], []))
        assert rec["state"] == "failed"
        assert rec["failed"] == [{"job": "build", "step": "Tests", "result": "failure",
                                  "log": os.path.join(world["store"], "runs", world["sha"],
                                                      "build.log")}]

    def test_act_past_its_bound_is_red_naming_the_bound(self, LC, world):
        rec = LC.run_commit(world["store"], world["sha"], "", "owner/repo", PLATFORM,
                            run=_fake_act([], [], raise_timeout=True))
        assert rec["state"] == "failed" and "past the run's bound" in rec["reason"]

    def test_act_reporting_no_job_is_an_error_never_a_verdict(self, LC, world):
        rec = LC.run_commit(world["store"], world["sha"], "", "owner/repo", PLATFORM,
                            run=_fake_act([], []))
        assert rec["state"] == "error" and "reported no job" in rec["reason"]

    def test_acts_containers_get_the_profile_and_nothing_broader(self, LC, world):
        """The operator's answer 1: a seccomp profile, least privilege. act's containers run
        with the profile, never privileged, with no capability added and no limit yet."""
        calls = []
        rec = LC.run_commit(world["store"], world["sha"], "", "owner/repo", PLATFORM,
                            run=_fake_act([("Run actions/checkout@v4", "success", 1),
                                           ("Tests", "success", 1)], calls),
                            seccomp="/etc/nmas/local-ci-seccomp.json")
        argv = calls[0]
        assert argv[argv.index("--container-options") + 1] == (
            "--security-opt seccomp=/etc/nmas/local-ci-seccomp.json")
        for broad in ("--privileged", "--container-cap-add", "SYS_ADMIN", "unconfined",
                      "--cpus", "--memory", "--userns", "--bind"):
            assert not any(broad in a for a in argv), (broad, argv)
        assert "--verbose" in argv, "a step skipped by its if is logged only at debug level"
        assert rec["confinement"]["seccomp"] == "/etc/nmas/local-ci-seccomp.json"

    def test_the_jobs_are_on_dockers_bridge_never_the_hosts_network(self, LC, world):
        """act's own default is `--network host` (its --help, 0.2.89): a job would share the
        host's loopback, where Mercury and its stores listen. The jobs go on Docker's bridge
        (online, the operator's answer 3), and act's artifact and cache servers bind to the
        bridge's gateway, not act's default of the host's LAN address."""
        calls = []
        LC.run_commit(world["store"], world["sha"], "", "owner/repo", PLATFORM,
                      run=_fake_act([("Run actions/checkout@v4", "success", 1),
                                     ("Tests", "success", 1)], calls))
        argv = calls[0]
        assert argv[argv.index("--network") + 1] == "bridge"
        assert argv[argv.index("--artifact-server-addr") + 1] == BRIDGE_GW
        assert argv[argv.index("--cache-server-addr") + 1] == BRIDGE_GW

    def test_a_bridge_that_cannot_be_read_is_an_error_never_a_run(self, LC, world):
        calls = []

        def run(argv, **kw):
            if argv[0] == "/usr/bin/docker":
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="no such network")
            return _fake_act([("Tests", "success", 1)], calls)(argv, **kw)
        rec = LC.run_commit(world["store"], world["sha"], "", "owner/repo", PLATFORM, run=run)
        assert rec["state"] == "error" and "bridge" in rec["reason"] and not calls, rec

    def test_every_record_says_its_limits_are_unset_and_its_network_online(self, LC, world):
        """Answers 3 and 4: online for now; CPU and memory limits after the first measured
        run. Each record says both, naming where the measurement is."""
        rec = LC.run_commit(world["store"], world["sha"], "", "owner/repo", PLATFORM,
                            run=_fake_act([("Run actions/checkout@v4", "success", 1),
                                           ("Tests", "success", 1)], []))
        assert rec["limits"].startswith("unset: ") and "first measured run" in rec["limits"]
        assert rec["network"] == "online"
        assert LC.CONTAINER_LIMITS == ""

    def test_acts_environment_dumps_are_not_kept(self, LC, world):
        """act -v logs each step's whole environment ("setupEnv => map[...]"); the store is
        world-readable, so those lines are dropped and every other line kept."""
        def run(argv, **kw):
            if argv[0] == "/usr/bin/docker":
                return _fake_docker(argv)
            if argv[0] != "/usr/local/bin/act":
                return _real(argv, **kw)
            out = kw["stdout"]
            out.write(json.dumps({"jobID": "build", "level": "debug", "stepID": ["0"],
                                  "msg": "setupEnv => map[ACT:true HOME:/root]"}) + "\n")
            for i, name in enumerate(("Run actions/checkout@v4", "Tests")):
                out.write(_line("build", i, name, "success") + "\n")
            return subprocess.CompletedProcess(argv, 0)
        LC.run_commit(world["store"], world["sha"], "", "owner/repo", PLATFORM, run=run)
        with open(os.path.join(world["store"], "runs", world["sha"], "act.jsonl")) as fh:
            kept = fh.read().splitlines()
        assert len(kept) == 2 and not any("setupEnv" in k for k in kept), kept

    def test_the_deploy_gate_reads_what_the_runner_writes(self, LC, world):
        """One shape, both ends: `nmas-deploy`'s `local_verdict` over the runner's own record."""
        LC.run_commit(world["store"], world["sha"], "", "owner/repo", PLATFORM,
                      run=_fake_act([("Run actions/checkout@v4", "success", 1),
                                     ("Tests", "success", 1)], []))
        D = _load("scripts/nmas-deploy", "nmas_deploy_for_local_ci")
        lv = D.local_verdict(str(world["dev"]), world["sha"],
                             {"path": world["store"], "owner": os.getuid()})
        assert lv["state"] == "passed", lv
        assert "2 step(s) of 1 job(s) passed" in lv["words"]


class TestTheRecord:
    def test_it_is_written_whole_and_renamed_into_place(self, LC, tmp_path):
        path = str(tmp_path / "verdicts" / ("a" * 40 + ".json"))
        LC.write_record(path, {"schema": 1, "state": "running", "sha": "a" * 40})
        LC.write_record(path, {"schema": 1, "state": "passed", "sha": "a" * 40})
        assert json.load(open(path))["state"] == "passed"
        assert os.listdir(tmp_path / "verdicts") == ["a" * 40 + ".json"]
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o644

    def test_a_record_that_cannot_be_read_is_never_overwritten_blind(self, LC, tmp_path):
        path = str(tmp_path / "b.json")
        with open(path, "w") as fh:
            fh.write('{"schema": 1, "sta')
        with pytest.raises(LC.Unreadable, match="could not be read"):
            LC.write_record(path, {"schema": 1, "state": "passed"})
        assert open(path).read() == '{"schema": 1, "sta'

    def test_only_a_full_sha_names_a_record(self, LC):
        with pytest.raises(ValueError):
            LC.verdict_path("/s", "../../etc/passwd")
        assert LC.verdict_path("/s", "c" * 40) == "/s/verdicts/" + "c" * 40 + ".json"


class TestSchedules:
    """The scheduled workflows' own crons (one definition: the workflow file's `schedule:`)."""

    # 2026-11-01 was a Sunday.
    SUN_1400 = 1793541600          # 2026-11-01T14:00:00Z

    def test_cron_matching(self, LC):
        assert LC.cron_matches("0 14 * * 0", self.SUN_1400)
        assert not LC.cron_matches("0 14 * * 0", self.SUN_1400 + 86400)
        assert LC.cron_matches("0 14 * * 7", self.SUN_1400)
        assert LC.cron_matches("47 3 * * *", self.SUN_1400 - 10 * 3600 - 13 * 60)
        assert LC.cron_matches("*/15 * * * *", self.SUN_1400 + 45 * 60)

    def test_a_workflow_whose_cron_fired_since_its_last_start_is_due(self, LC):
        wfs = {"mutation-nightly.yml": {"on": {"schedule": [{"cron": "0 14 * * 0"}]}},
               "coverage-nightly.yml": {True: {"schedule": [{"cron": "47 3 * * *"}]}},
               "other.yml": {"on": {"push": None}}}
        now = self.SUN_1400 + 600
        due = LC.due_schedules(wfs, {"coverage-nightly.yml": now - 60}, now)
        assert due == [("mutation-nightly.yml", "0 14 * * 0", self.SUN_1400)]
        assert LC.due_schedules(wfs, {"coverage-nightly.yml": now - 60,
                                      "mutation-nightly.yml": self.SUN_1400 + 1}, now) == []

    def test_the_repositorys_scheduled_workflows_are_found(self, LC):
        docs = {}
        for name in ("coverage-nightly.yml", "mutation-nightly.yml", "ci.yml"):
            with open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8") as fh:
                docs[name] = yaml.safe_load(fh)
        due = {n for n, _c, _f in LC.due_schedules(docs, {}, self.SUN_1400 + 60)}
        assert due == {"coverage-nightly.yml", "mutation-nightly.yml"}

    def test_the_quiet_window(self, LC):
        at = 1793521800                # 2026-11-01T08:30:00Z
        assert LC.in_quiet("08:30-09:10", at) and LC.in_quiet("08:30-09:10", at + 39 * 60)
        assert not LC.in_quiet("08:30-09:10", at + 40 * 60) and not LC.in_quiet("", at)
        assert LC.in_quiet("23:00-01:00", at - 8 * 3600 - 30 * 60 + 24 * 3600 - 1800)


class TestTheSelfTest:
    def test_it_names_what_the_host_lacks(self, LC, tmp_path):
        problems = LC.self_test(str(tmp_path / "absent"),
                                {"NMAS_LOCAL_CI_ORIGIN": "ssh://x/y",
                                 "NMAS_LOCAL_CI_PLATFORM": "ubuntu-24.04=example/runner:latest"},
                                run=lambda *a, **k: subprocess.CompletedProcess(a, 0))
        joined = "; ".join(problems)
        assert "does not exist" in joined
        assert "NMAS_LOCAL_CI_ORIGIN is not an https:// or file:// URL" in joined
        assert "does not pin its image by digest" in joined
        assert "NMAS_LOCAL_CI_SECCOMP names no seccomp profile" in joined

    @pytest.mark.parametrize("platform,pinned", [
        ("ubuntu-24.04=sha256:" + "b" * 64, True),            # the image built on the host
        ("ubuntu-24.04=example/runner@sha256:" + "c" * 64, True),
        ("ubuntu-24.04=example/runner:latest", False),
        ("ubuntu-24.04=sha256:" + "b" * 63, False)])
    def test_the_job_image_is_pinned_by_its_id_or_its_digest(self, LC, tmp_path, platform,
                                                             pinned):
        problems = LC.self_test(str(tmp_path), {"NMAS_LOCAL_CI_PLATFORM": platform},
                                run=lambda *a, **k: subprocess.CompletedProcess(a, 0))
        said = any("does not pin its image by digest" in p for p in problems)
        assert said is not pinned, problems

    def _env(self, profile):
        return {"NMAS_LOCAL_CI_ORIGIN": "https://example.invalid/o/r.git",
                "NMAS_LOCAL_CI_PLATFORM": PLATFORM, "NMAS_LOCAL_CI_SECCOMP": str(profile)}

    def test_the_profile_must_be_roots_alone_and_least_privilege(self, LC, tmp_path):
        profile = tmp_path / "seccomp.json"
        good = LC.seccomp_profile(_excerpt())
        profile.write_text(json.dumps(good))
        profile.chmod(0o644)
        def ok(argv, **_kw):
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        probs = LC.self_test(str(tmp_path), self._env(profile), run=ok, owner=os.getuid())
        assert not [p for p in probs if "seccomp" in p], probs
        profile.write_text(json.dumps(dict(good, defaultAction="SCMP_ACT_ALLOW")))
        probs = LC.self_test(str(tmp_path), self._env(profile), run=ok, owner=os.getuid())
        assert any("allows by default" in p for p in probs), probs
        wide = json.loads(json.dumps(good))
        wide["syscalls"].append({"names": ["setns", "mount"], "action": "SCMP_ACT_ALLOW"})
        profile.write_text(json.dumps(wide))
        probs = LC.self_test(str(tmp_path), self._env(profile), run=ok, owner=os.getuid())
        assert any("allows mount, setns with no condition" in p for p in probs), probs
        profile.write_text(json.dumps(good))
        probs = LC.self_test(str(tmp_path), self._env(profile), run=ok, owner=os.getuid() + 1)
        assert any(f"{profile} is not root's alone" in p for p in probs), probs

    def test_the_deep_self_test_starts_both_browsers_in_the_job_image(self, LC, tmp_path):
        """The operator's answer 2: the job image carries Firefox and geckodriver. Asked by
        running them in the image, with no network, never by reading a label."""
        profile = tmp_path / "seccomp.json"
        profile.write_text(json.dumps(LC.seccomp_profile(_excerpt())))
        profile.chmod(0o644)
        seen = []

        def run(argv, **kw):
            seen.append(argv)
            if "run" in argv:
                return subprocess.CompletedProcess(argv, 127, stdout="",
                                                   stderr="firefox: not found")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        probs = LC.self_test(str(tmp_path), self._env(profile), run=run, owner=os.getuid(),
                             deep=True)
        started = [a for a in seen if "run" in a][0]
        assert started[:3] == ["/usr/bin/docker", "run", "--rm"]
        assert "--network" in started and started[started.index("--network") + 1] == "none"
        assert "firefox --version" in started[-1] and "geckodriver --version" in started[-1]
        assert any("cannot start Firefox and geckodriver" in p and "firefox: not found" in p
                   for p in probs), probs
        seen.clear()
        LC.self_test(str(tmp_path), self._env(profile), run=run, owner=os.getuid())
        assert not [a for a in seen if "run" in a], "the per-run check starts no container"


FIX = os.path.join(ROOT, "tests", "fixtures", "act")


def _fixture_log(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read().splitlines()


def _fixture_wf(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class TestActsCapturedLog:
    """act 0.2.89's own `--json -v` log over the two probe workflows beside it (captured on the
    laptop 2026-11-03, self-hosted, a selection of lines, none rewritten)."""

    def test_the_fixtures_are_what_they_say(self, LC):
        lines = [json.loads(x) for name in ("act-0.2.89-matrix.jsonl",
                                            "act-0.2.89-soft-hard.jsonl",
                                            "act-0.2.89-setup-failed.jsonl")
                 for x in _fixture_log(name)]
        assert len(lines) >= 35
        assert not any("setupEnv" in x.get("msg", "") for x in lines)
        assert sum(1 for x in lines if x.get("stepResult") == "skipped") == 6

    def test_a_matrix_run_is_judged_shard_by_shard(self, LC):
        v = LC.judge(_fixture_wf("probe.yml"),
                     LC.read_act_log(_fixture_log("act-0.2.89-matrix.jsonl")))
        assert v["state"] == "failed" and not v["not_run"], v
        assert v["failed"] == [{"job": "test (b)", "step": "Fails on b", "result": "failure"}]
        steps = {j["name"]: {s["name"]: s["result"] for s in j["steps"]} for j in v["jobs"]}
        assert steps["test (a)"] == {"Say the shard": "success",
                                     "Skipped under act": "not run (act)",
                                     "Fails but non-gating": "failure", "Fails on b": "success",
                                     "Only on a": "success"}
        assert steps["test (b)"]["Only on a"] == "skipped"
        assert steps["scope"] == {"Pick the shards": "success"}

    def test_skips_by_if_and_under_act_and_a_hard_failure(self, LC):
        v = LC.judge(_fixture_wf("probe2.yml"),
                     LC.read_act_log(_fixture_log("act-0.2.89-soft-hard.jsonl")))
        assert v["failed"] == [{"job": "hard", "step": "Fails", "result": "failure"}]
        assert v["not_run"] == [{"job": "soft", "step": "Skipped under act",
                                 "why": "the workflow skips it under act, and its env names "
                                        "no NMAS_ACT_NOT_GATING"}]
        steps = {j["name"]: {s["name"]: s["result"] for s in j["steps"]} for j in v["jobs"]}
        assert steps["soft"]["Skipped by its if"] == "skipped"
        assert steps["hard"] == {"Fails": "failure", "Never reached": "skipped",
                                 "Always runs": "success"}

    def test_a_job_whose_set_up_failed_is_failed_naming_it(self, LC):
        """Probe 3: the job image absent from Docker's store. act's own `Set up job` (a
        `stepid` line, not `stepID`) failed, and nothing after it ran."""
        v = LC.judge(_fixture_wf("probe2.yml"),
                     LC.read_act_log(_fixture_log("act-0.2.89-setup-failed.jsonl")))
        assert v["state"] == "failed"
        assert v["failed"] == [{"job": "soft", "step": "Set up job", "result": "failure"}]
        assert [n["job"] for n in v["not_run"]] == ["hard"], v["not_run"]

    def test_acts_times_carry_the_clocks_offset(self, LC):
        assert LC._parse_iso("2026-11-03T16:21:09-07:00") == 1793748069
        assert LC._parse_iso("2026-11-03T23:21:09Z") == 1793748069
        assert LC._parse_iso("not a time") is None


def _excerpt():
    """Docker's default seccomp profile, moby/profiles seccomp/v0.1.0 (the version Docker
    29.1.3 vendors; the file's sha256 01536f1d1df9...8301e28): its default action and every
    rule naming clone, clone3 or unshare, verbatim, and its first rule cut to four names."""
    with open(os.path.join(FIX, "seccomp-default-excerpt.json"), encoding="utf-8") as fh:
        return json.load(fh)


#: The namespace flags of clone(2) and unshare(2), from the kernel's uapi/linux/sched.h.
NEWNS, NEWCGROUP, NEWUTS, NEWIPC = 0x00020000, 0x02000000, 0x04000000, 0x08000000
NEWUSER, NEWPID, NEWNET = 0x10000000, 0x20000000, 0x40000000


def _allows(rule, flags):
    """Whether one masked-equal rule passes *flags* (the kernel's test: arg & mask == value)."""
    (arg,) = rule["args"]
    assert arg["op"] == "SCMP_CMP_MASKED_EQ" and arg["index"] == 0
    return flags & arg["value"] == arg.get("valueTwo", 0)


class TestTheSeccompProfile:
    """The operator's answer 1: a seccomp profile, least privilege. The suite confines itself
    with `unshare -rn` (scripts/nmas-test), which Docker's default profile refuses without
    CAP_SYS_ADMIN; the profile lets exactly that through."""

    def test_it_is_dockers_default_plus_one_rule(self, LC):
        base = _excerpt()
        prof = LC.seccomp_profile(base)
        added = [s for s in prof["syscalls"] if s not in base["syscalls"]]
        assert [s for s in base["syscalls"] if s not in prof["syscalls"]] == []
        assert len(added) == 1 and prof["defaultAction"] == base["defaultAction"]
        (rule,) = added
        assert rule["names"] == ["unshare"] and rule["action"] == "SCMP_ACT_ALLOW"
        assert rule["excludes"] == {"caps": ["CAP_SYS_ADMIN"]}

    def test_only_a_user_and_a_network_namespace_are_let_through(self, LC):
        (rule,) = [s for s in LC.seccomp_profile(_excerpt())["syscalls"]
                   if s not in _excerpt()["syscalls"]]
        assert _allows(rule, NEWUSER | NEWNET) and _allows(rule, NEWUSER) and _allows(rule, 0)
        for other in (NEWNS, NEWCGROUP, NEWUTS, NEWIPC, NEWPID):
            assert not _allows(rule, other | NEWUSER | NEWNET), hex(other)

    def test_clone_keeps_the_defaults_own_rules(self, LC):
        base, prof = _excerpt(), LC.seccomp_profile(_excerpt())
        def pick(p):
            return [s for s in p["syscalls"] if s["names"] in (["clone"], ["clone3"])]
        assert pick(prof) == pick(base) and len(pick(base)) == 3

    @pytest.mark.parametrize("breaks", ["allows by default", "no clone rule",
                                        "unshare already allowed", "another clone mask"])
    def test_a_default_of_another_shape_is_refused_never_guessed_at(self, LC, breaks):
        base = _excerpt()
        if breaks == "allows by default":
            base["defaultAction"] = "SCMP_ACT_ALLOW"
        elif breaks == "no clone rule":
            base["syscalls"] = [s for s in base["syscalls"] if s["names"] != ["clone"]]
        elif breaks == "unshare already allowed":
            base["syscalls"].append({"names": ["unshare"], "action": "SCMP_ACT_ALLOW"})
        else:
            for s in base["syscalls"]:
                if s["names"] == ["clone"]:
                    s["args"][0]["value"] = 0x7E000000
        with pytest.raises(LC.ProfileShape):
            LC.seccomp_profile(base)

    def test_the_command_writes_it_whole_naming_its_source(self, LC, tmp_path, capsys):
        src, out = tmp_path / "default.json", tmp_path / "etc" / "local-ci-seccomp.json"
        src.write_text(json.dumps(_excerpt()))
        assert LC.main(["seccomp-profile", "--from", str(src), "--out", str(out)],
                       env={"NMAS_LOCAL_CI_STORE": str(tmp_path)}) == 0
        assert json.loads(out.read_text()) == LC.seccomp_profile(_excerpt())
        assert stat.S_IMODE(os.stat(out).st_mode) == 0o644
        said = capsys.readouterr().out
        assert "one rule added" in said and str(src) in said


class TestTheJobImage:
    """deploy/local-ci/runner.Dockerfile (the operator's answer 2): act's medium image pinned
    by digest, Firefox and geckodriver each pinned by version and checked against a published
    sha256, and what GitHub's image carries that the suite's confinement needs (`ip`)."""

    @pytest.fixture(scope="class")
    def text(self):
        with open(os.path.join(ROOT, "deploy", "local-ci", "runner.Dockerfile"),
                  encoding="utf-8") as fh:
            return fh.read()

    def _arg(self, text, name):
        m = [ln.split("=", 1)[1] for ln in text.splitlines() if ln.startswith(f"ARG {name}=")]
        assert len(m) == 1, name
        return m[0]

    def test_the_base_is_pinned_by_digest(self, text):
        assert re.fullmatch(r"[\w./-]+@sha256:[0-9a-f]{64}", self._arg(text, "BASE"))
        assert "FROM ${BASE}" in text.splitlines()

    @pytest.mark.parametrize("tool", ["FIREFOX", "GECKODRIVER"])
    def test_each_browser_is_pinned_and_checked(self, text, tool):
        assert re.fullmatch(r"\d+\.\d+(\.\d+)?", self._arg(text, f"{tool}_VERSION"))
        assert re.fullmatch(r"[0-9a-f]{64}", self._arg(text, f"{tool}_SHA256"))
        assert f'echo "${{{tool}_SHA256}}  ' in text and "sha256sum -c -" in text

    def test_it_carries_what_the_suites_confinement_runs(self, text):
        """scripts/nmas-test runs `ip link set lo up` inside the namespace; act's medium image
        has no `ip` (measured 2026-11-03), so the image installs iproute2."""
        with open(os.path.join(ROOT, "scripts", "nmas-test"), encoding="utf-8") as fh:
            assert "ip link set lo up" in fh.read()
        installs = " ".join(ln for ln in text.splitlines() if "install" in ln or
                            ln.strip().startswith(("lib", "fonts")))
        assert re.search(r"\biproute2\b", installs), installs


class TestTheOverrideIsTheTerminals:
    """The operator's answer 5: the CI override is the terminal's alone, with no in-app button.
    `nmas-deploy --override-ci-red "<reason>"` is its one door."""

    def test_the_updater_never_passes_one(self):
        with open(os.path.join(ROOT, "deploy", "update", "nmas-update"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "ci_verdict"]
        assert calls, "the updater's gate call was not found: the scan has nothing to hold"
        for c in calls:
            assert len(c.args) == 2 and not c.keywords, ast.dump(c)

    def test_nothing_the_app_serves_names_it(self):
        names = ("override-ci-red", "override_ci_red")
        from tests.source_index import tracked

        read, found = 0, []
        for p in tracked("routes", "modules", "templates", "static/js", "app.py",
                         suffix=(".py", ".html", ".js")):
            with open(p, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            read += 1
            found += [os.path.relpath(p, ROOT) for n in names if n in text]
        assert read > 200, read
        assert found == [], found
        with open(os.path.join(ROOT, "scripts", "nmas-deploy"), encoding="utf-8") as fh:
            assert "--override-ci-red" in fh.read(), "the planted case: the terminal's door"


class TestTheWorkflowsUnderAct:
    """A step that changes the host kernel is GitHub's throwaway VM's to run, never a job
    container's on this host: each is skipped under act (`if: ${{ !env.ACT }}`), saying why in
    its own env (NMAS_ACT_NOT_GATING), so the verdict names it and still counts it."""

    def _steps(self):
        out = []
        folder = os.path.join(ROOT, ".github", "workflows")
        for name in sorted(os.listdir(folder)):
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
            for job_id, job in (doc.get("jobs") or {}).items():
                for s in job.get("steps") or []:
                    out.append((name, job_id, s))
        return out

    def test_every_step_that_changes_the_kernel_says_why_it_is_skipped(self, LC):
        kernel = [(n, j, s) for n, j, s in self._steps() if "sysctl -w" in (s.get("run") or "")]
        assert len(kernel) >= 3, "the floor: ci.yml and the two nightlies each set one"
        for name, job, s in kernel:
            assert LC.ACT_GUARD.search(str(s.get("if") or "")), (name, job, s.get("name"))
            why = (s.get("env") or {}).get(LC.ACT_NOT_GATING) or ""
            assert len(why.split()) >= 8, (name, job, s.get("name"), why)

    def test_the_real_ci_yml_is_then_passed_naming_the_step(self, LC, ci_yml):
        i = next(i for i, s in enumerate(ci_yml["jobs"]["test"]["steps"])
                 if "sysctl -w" in (s.get("run") or ""))
        lines = [ln for ln in _ci_log(ci_yml) if not (
            json.loads(ln).get("jobID") == "test"
            and json.loads(ln).get("stepID") == [str(ci_yml["jobs"]["test"]["steps"][i].get("id")
                                                     or i)])]
        for shard in ("browser1", "browser2", "browser3", "a", "b"):
            lines.append(_line("test", i, ci_yml["jobs"]["test"]["steps"][i]["name"], "skipped",
                               matrix={"shard": shard}))
        v = LC.judge(ci_yml, LC.read_act_log(lines))
        assert v["state"] == "passed", (v["failed"][:2], v["not_run"][:2])
        step = v["jobs"][0]["steps"][i] if v["jobs"][0]["job_id"] == "test" else next(
            j for j in v["jobs"] if j["job_id"] == "test")["steps"][i]
        assert step["result"] == "not run (act)" and step["non_gating"] is True
