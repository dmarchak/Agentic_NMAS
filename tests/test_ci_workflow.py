"""The CI workflow can read only this repository, installs the host's versions,
and reports coverage without gating on it (NSOT_CI.md, P.4 step 3).

The config repository holds plaintext device secrets by design, so a runner
reading it would process device credentials. What would let a workflow reach
it: a `repository:` input, a secret (a token or deploy key), or broader
permissions. This test fails on each.

**Its limit, stated:** one commit that edits the workflow AND this test passes.
The second, independent layer is Actions disabled in the config repository's
own settings, so nothing can run THERE on a GitHub-hosted runner at all.
"""

import os
import re

import pytest
import yaml

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOWS = tracked(os.path.join(ROOT, ".github", "workflows"), suffix=(".yml", ".yaml"),
                    recursive=False)


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh), fh.name


def _on(doc) -> list:
    """A workflow's triggers (YAML 1.1 reads `on` as True)."""
    triggers = doc.get(True) or doc.get("on") or {}
    return list(triggers) if isinstance(triggers, (dict, list)) else [triggers]


def _on_push(path) -> bool:
    doc, _ = _load(path)
    return "push" in _on(doc)


#: The per-push suite: every workflow a push triggers (by that property, not by name). The
#: nightly mutation run is not one: no push starts it, it runs no suite, and its own checks are
#: tests/test_nmas_mutation.py's. Every workflow, it included, still meets the checks above
#: these: a read-only token, no other repository, the host's versions.
SUITE_WORKFLOWS = [p for p in WORKFLOWS if _on_push(p)]


def test_the_per_push_population_holds_ci():
    assert any(p.endswith(os.sep + "ci.yml") for p in SUITE_WORKFLOWS), SUITE_WORKFLOWS


def _walk(node):
    """Every (key, value) pair and every string, anywhere in the document."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _strings(node):
    """Every key and string VALUE in the parsed document. Parsed, not the raw
    text: the workflow's own comment names the config repository to explain
    why it is never read, and the first version of this test matched it."""
    for key, value in _walk(node):
        yield str(key)
        if isinstance(value, str):
            yield value


def _steps(doc):
    return [s for job in (doc.get("jobs") or {}).values() for s in job.get("steps", [])]


def test_the_scan_finds_a_workflow_and_a_checkout():
    """Floor: an empty listing would pass every test below."""
    assert WORKFLOWS, "no workflow found"
    checkouts = [s for path in WORKFLOWS for s in _steps(_load(path)[0])
                 if str(s.get("uses", "")).startswith("actions/checkout")]
    assert checkouts


#: The one job whose token may also read Actions, each with why: `actions: read` is read-only and
#: this repository's alone (a token reaches no other repository through it), the permission
#: actions/download-artifact needs to fetch another run's artifact.
READS_ACTIONS = {
    ("mutation-nightly.yml", "mutate"): "the newest coverage nightly's drill-down (C796, C834)",
}


def _permission_problems(workflow: str, doc: dict) -> list:
    """What in a workflow's token is more than reading this repository's contents (and, for a
    job in READS_ACTIONS, its Actions)."""
    problems = []
    if doc.get("permissions") != {"contents": "read"}:
        problems.append(f"the workflow's permissions: {doc.get('permissions')}")
    for name, job in (doc.get("jobs") or {}).items():
        allowed = [None, {"contents": "read"}]
        if (workflow, name) in READS_ACTIONS:
            allowed.append({"contents": "read", "actions": "read"})
        if job.get("permissions") not in allowed:
            problems.append(f"job {name}: {job.get('permissions')}")
    return problems


@pytest.mark.parametrize("path", WORKFLOWS)
def test_the_token_is_read_only(path):
    doc, _ = _load(path)
    assert _permission_problems(os.path.basename(path), doc) == []


def test_the_job_reading_actions_is_the_one_listed_and_nothing_else_gains():
    """The listed job's token reads Actions and its contents, nothing more; controls: the same
    permission planted on another job, and a write planted on the listed one, are each named."""
    for wf, job in READS_ACTIONS:
        doc, _ = _load(os.path.join(ROOT, ".github", "workflows", wf))
        assert doc["jobs"][job]["permissions"] == {"contents": "read", "actions": "read"}
    ci, _ = _load(os.path.join(ROOT, ".github", "workflows", "ci.yml"))
    ci["jobs"]["test"]["permissions"] = {"contents": "read", "actions": "read"}
    assert _permission_problems("ci.yml", ci) == [
        "job test: {'contents': 'read', 'actions': 'read'}"]
    night, _ = _load(os.path.join(ROOT, ".github", "workflows", "mutation-nightly.yml"))
    night["jobs"]["mutate"]["permissions"] = {"contents": "read", "actions": "write"}
    assert _permission_problems("mutation-nightly.yml", night) == [
        "job mutate: {'contents': 'read', 'actions': 'write'}"]


@pytest.mark.parametrize("path", WORKFLOWS)
def test_it_can_reach_no_other_repository(path):
    doc, _ = _load(path)
    strings = list(_strings(doc))
    assert len(strings) >= 20, len(strings)
    assert not [t for t in strings if "secrets." in t], "a secret is how a workflow reaches another repository"
    assert not [t for t in strings if "nsot-config" in t], "the config repository is never named"
    for key, _value in _walk(doc):
        assert key not in ("repository", "token", "ssh-key"), key
    for step in _steps(doc):
        if str(step.get("uses", "")).startswith("actions/checkout"):
            assert (step.get("with") or {}).get("persist-credentials") is False, step


@pytest.mark.parametrize("path", WORKFLOWS)
def test_it_installs_the_hosts_versions_and_never_gates_on_coverage(path):
    raw = open(path, encoding="utf-8").read()
    # Section 8.2: the host's venv installs these exact files; without --no-deps a resolver
    # installs something other than the lock, and without --require-hashes other bytes.
    assert "pip install --require-hashes --no-deps -r requirements.lock" in raw
    assert "-r requirements.txt" not in raw, "requirements.txt is the input; the lock is installed"
    assert "--cov-fail-under" not in raw and "fail_under" not in raw


@pytest.mark.parametrize("path", SUITE_WORKFLOWS)
def test_superseded_runs_are_cancelled_except_on_main_and_every_push_runs(path):
    """C440 (the operator, 2026-10-04): a run on main is never cancelled, since the Update
    button needs every commit's verdict (C436); a run on any other ref still is. C1287 (the
    operator, 2026-10-18): no push or pull request is filtered by path, so a Markdown-only
    commit (CLAUDE.md among them) runs tests/test_claude_md.py and job a's range checks."""
    doc, _ = _load(path)
    assert (doc.get("concurrency") or {}).get("cancel-in-progress") == \
        "${{ github.ref != 'refs/heads/main' }}"
    # C1294 (the operator, 2026-10-18): on main every commit is its own group, so no main run
    # waits pending behind another and is cancelled when a third queues.
    assert (doc.get("concurrency") or {}).get("group") == \
        "ci-${{ github.ref == 'refs/heads/main' && github.sha || github.ref }}"
    triggers = doc.get(True) or doc.get("on")      # YAML 1.1 reads `on` as True
    assert "push" in triggers and "pull_request" in triggers, triggers
    for event in ("push", "pull_request"):
        filters = set(triggers.get(event) or {}) & {"paths", "paths-ignore", "branches-ignore"}
        assert not filters, f"{event} is filtered by {sorted(filters)}: some pushes run nothing"


@pytest.mark.parametrize("path", SUITE_WORKFLOWS)
def test_the_suite_runs_confined_and_never_unconfined(path):
    """C46: CI runs the suite through scripts/nmas-test, which requires the
    network namespace it creates. Parsed values, not the raw text."""
    doc, _ = _load(path)
    runs = [str(s.get("run", "")) for s in _steps(doc)]
    # The runner by its whole name: scripts/nmas-test-weakening-check is another program.
    suite = [r for r in runs if "pytest" in r or re.search(r"(?<![\w-])nmas-test(?![\w-])", r)]
    assert suite, "no step runs the suite"
    for run in suite:
        assert run.lstrip().startswith("scripts/nmas-test"), run
        assert "--allow-unconfined" not in run, run


@pytest.mark.parametrize("path", SUITE_WORKFLOWS)
def test_it_installs_the_test_tools_the_host_installs(path):
    """C45: the runner that schedules the tests is pinned once, for both."""
    raw = open(path, encoding="utf-8").read()
    assert "pip install --no-deps -r requirements-test.txt" in raw
    assert "-n auto" in raw


def test_a_failed_test_is_annotated_under_actions(tmp_path):
    """A red run must say WHICH test from the public API (annotations), not
    only in the log, which needs authentication. Driven as a real nested
    pytest run under GITHUB_ACTIONS=true with one failing test."""
    import os
    import subprocess
    import sys

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    t = tmp_path / "test_x_fails.py"
    t.write_text("def test_it_fails():\n    assert 1 == 2, 'the planted failure'\n")
    env = dict(os.environ, GITHUB_ACTIONS="true")
    # The planted file lives outside tests/, so the suite's conftest is loaded
    # as a plugin: the hook under test is the shipped one, in its own process.
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          "-p", "tests.conftest", "--rootdir", root,
                          "-c", os.path.join(root, "pytest.ini"), str(t)],
                         cwd=root, env=env, capture_output=True, text=True, timeout=120)
    lines = [l for l in out.stdout.splitlines() if l.startswith("::error title=")]
    assert any("test_it_fails" in l and "planted failure" in l for l in lines), out.stdout[-2000:]


def test_the_coverage_job_reports_line_coverage_over_the_four_shards_combined():
    """One line figure, from the COMBINED data (never one shard's), over the measured code, in
    the log and the job summary: after the combine, before the report."""
    doc, _ = _load(os.path.join(ROOT, ".github", "workflows", "ci.yml"))
    steps = doc["jobs"]["coverage"]["steps"]
    names = [s.get("name", "") for s in steps]
    combine = names.index("Combine them")
    total = names.index("Line coverage, every test, the four shards combined")
    assert combine < total < names.index("The report and the ratchet")
    run = steps[total]["run"]
    assert "--data-file=.coverage " in run and "--format=total" in run
    assert "--include='modules/*,routes/*,app.py'" in run and "GITHUB_STEP_SUMMARY" in run
    assert "coverage combine --keep --data-file=.coverage measured/.coverage.*" in \
        steps[combine]["run"]


def _tests_step(doc):
    return next(s for s in doc["jobs"]["test"]["steps"]
                if str(s.get("name", "")).startswith("Tests"))


class TestAPushMeasuresByTierAndTheNightPerTest:
    """C773 (2026-10-14): a push's tests step ran twice as long once it measured per test with
    branches, which forces coverage's C tracer. A push now measures each test's run phase by tier
    (tests/coverage_tiers.py) with sys.monitoring, lines only; the per-test drill-down and branch
    figures are the nightly coverage run's, on the same shards and setup."""

    def _docs(self):
        wf = os.path.join(ROOT, ".github", "workflows")
        return (_load(os.path.join(wf, "ci.yml"))[0],
                _load(os.path.join(wf, "coverage-nightly.yml"))[0])

    def test_a_push_measures_by_tier_with_sys_monitoring_and_no_per_test_argument(self):
        ci, _night = self._docs()
        step = _tests_step(ci)
        assert step["env"]["COVERAGE_CORE"] == "sysmon"
        assert step["env"]["NMAS_COVERAGE_TIERS"] == "1"
        assert "--cov-context" not in step["run"] and "--cov-branch" not in step["run"], \
            "either forces the C tracer"
        keep = next(s for s in ci["jobs"]["test"]["steps"]
                    if str(s.get("name", "")).startswith("Keep this shard"))
        assert ".coverage.${{ matrix.shard }}*" in keep["with"]["path"], \
            "the tier-labelled data files travel with the shard's"

    def test_the_night_measures_per_test_with_branches_and_never_on_a_push(self):
        _ci, night = self._docs()
        assert set(_on(night)) == {"schedule", "workflow_dispatch"}
        step = _tests_step(night)
        assert "--cov-context=test" in step["run"] and "--cov-branch" in step["run"]
        assert "NMAS_COVERAGE_TIERS" not in step["env"]
        keep = night["jobs"]["report"]["steps"][-1]
        assert keep["with"]["name"] == "coverage-drilldown"

    def test_the_nights_per_test_bound_holds_its_slowest_setup_under_the_c_tracer(self):
        """C1616 (2026-10-23): under the C tracer a setup measured about 180 s on the runner
        passed pytest.ini's 120 s, and the dump inside an xdist worker took it down (C647's
        shape). The night's bound is 2.5x that; a push's stays pytest.ini's."""
        ci, night = self._docs()
        assert "-o faulthandler_timeout=450" in _tests_step(night)["run"]
        assert "faulthandler_timeout" not in _tests_step(ci)["run"]

    def test_the_nights_tests_stand_on_cis_setup_step_for_step(self):
        ci, night = self._docs()
        ci_steps, n_steps = ci["jobs"]["test"]["steps"], night["jobs"]["test"]["steps"]
        before = ci_steps[:ci_steps.index(_tests_step(ci))]
        runs = {s["run"] for s in n_steps if "run" in s}
        missing = [s.get("name") for s in before if "run" in s and s["run"] not in runs]
        assert len([s for s in before if "run" in s]) >= 7 and missing == [], missing   # 7 today
        assert night["jobs"]["test"]["strategy"] == ci["jobs"]["test"]["strategy"]

    def test_the_nights_tests_take_cis_actions_with_their_options(self):
        """C786 (the first nightly coverage run, 2026-10-14): the night checked out shallow
        where CI checks out the whole history (`fetch-depth: 0`), so the tests that read the
        shipped templates' history skipped there (8 in shard b) and what only they reach went
        unmeasured. The run-step comparison above never looked at a `uses:` step's options."""
        ci, night = self._docs()
        ci_steps = ci["jobs"]["test"]["steps"]
        before = ci_steps[:ci_steps.index(_tests_step(ci))]
        night_uses = [(s["uses"], s.get("with") or {}) for s in night["jobs"]["test"]["steps"]
                      if "uses" in s]
        wanted = [(s["uses"], s.get("with") or {}) for s in before if "uses" in s]
        assert len(wanted) >= 2, wanted                        # checkout and setup-python today
        missing = [w for w in wanted if w not in night_uses]
        assert missing == [], f"CI's actions the night lacks, or takes with other options: " \
                              f"{missing}"

    def test_the_push_names_the_drilldown(self):
        ci, _night = self._docs()
        steps = ci["jobs"]["coverage"]["steps"]
        names = [s.get("name", "") for s in steps]
        where = steps[names.index("Where the per-test drill-down is")]
        assert "coverage-nightly.yml/runs?status=success" in where["run"]
        assert "secrets." not in where["run"] and "token" not in where["run"].lower(), \
            "the public API: this token stays contents: read"
        report = steps[names.index("The report and the ratchet")]
        assert '--drilldown "$DRILLDOWN"' in report["run"]
        assert report["env"]["DRILLDOWN"] == "${{ steps.drilldown.outputs.line }}"


# ── C1637 and C1631: a setup step that reaches the network is cached and bounded ──────────────

#: A setup step that reaches a PACKAGE MIRROR: apt, or PGDG's repository script. Measured slow
#: on 22 of 60 shard-steps (CI #1097 to #1111): it must run only on its cache's miss, and is
#: bounded at MIRROR_MINUTES, just over the slowest completion measured (566 s, promtool), so a
#: hang (1,563 s, CI #1106) fails that step by name instead of the job (C1637, C1631).
MIRROR = re.compile(r"\bapt-get\b|apt\.postgresql\.org\.sh")
MIRROR_MINUTES = 10
#: A setup step that reaches the network but was never measured slow: pip's installs (7 to 17 s
#: on CI and both nights) and the drill-down's API read (0 to 1 s). Bounded, not cached: each
#: bound about 2.5 times its slowest measurement, in whole minutes (C1631).
FETCH = {"pip install": 2, "curl ": 1}
#: A command line that reaches the network: each one runs under `scripts/nmas-retry` (one retry
#: on failure, C1631), or is a `curl` with its own `--retry`.
NETWORK_COMMAND = re.compile(r"\bapt-get (update|install|download)\b|apt\.postgresql\.org\.sh"
                             r"|\bpip install\b|\bcurl\b")


def unretried(run: str) -> list:
    """The lines of *run* that reach the network with no retry."""
    return [ln.strip() for ln in run.splitlines()
            if NETWORK_COMMAND.search(ln)
            and "nmas-retry" not in ln and "$R" not in ln
            and not ("curl" in ln and "--retry" in ln)]


def network_gaps(doc, job: str) -> list:
    """Each step of *job* that reaches a mirror and is not run only on a cache miss or is not
    bounded at MIRROR_MINUTES at most, each other network step without its FETCH bound, each
    network command line with no retry, and each cache step whose miss no downloading step
    names."""
    steps = doc["jobs"][job]["steps"]
    caches = {s["id"] for s in steps
              if str(s.get("uses", "")).startswith("actions/cache@") and s.get("id")}
    gaps, guarded = [], set()
    for s in steps:
        run, name = s.get("run", ""), s.get("name") or s.get("run", "")[:40]
        minutes = s.get("timeout-minutes")
        gaps += [f"{name}: '{ln}' reaches the network with no retry" for ln in unretried(run)]
        if MIRROR.search(run):
            hit = [c for c in caches
                   if f"steps.{c}.outputs.cache-hit != 'true'" in str(s.get("if", ""))]
            if not hit:
                gaps.append(f"{name}: reaches a mirror on every run (no cache-miss condition)")
            guarded.update(hit)
            if not isinstance(minutes, (int, float)) or minutes > MIRROR_MINUTES:
                gaps.append(f"{name}: timeout-minutes {minutes!r}, not at most {MIRROR_MINUTES}")
            continue
        for word, bound in FETCH.items():
            if word in run and (not isinstance(minutes, (int, float)) or minutes > bound):
                gaps.append(f"{name}: reaches the network ({word.strip()}) with timeout-minutes "
                            f"{minutes!r}, not at most {bound}")
    gaps += [f"cache {c}: no step downloads on its miss" for c in sorted(caches - guarded)]
    return gaps


SETUP_JOBS = [("ci.yml", "test"), ("coverage-nightly.yml", "test"),
              ("mutation-nightly.yml", "mutate")]
#: Every job of every workflow, by a scan: the coverage jobs install and ask the API too.
EVERY_JOB = [(os.path.basename(p), j) for p in WORKFLOWS for j in _load(p)[0].get("jobs", {})]


@pytest.mark.parametrize("name,job", SETUP_JOBS)
def test_every_network_setup_step_is_cached_and_bounded(name, job):
    doc, _ = _load(os.path.join(ROOT, ".github", "workflows", name))
    steps = doc["jobs"][job]["steps"]
    assert len([s for s in steps if MIRROR.search(s.get("run", ""))]) >= 2, "floor"
    assert network_gaps(doc, job) == []


@pytest.mark.parametrize("name,job", EVERY_JOB)
def test_every_job_s_network_steps_are_bounded_and_retried(name, job):
    doc, _ = _load(os.path.join(ROOT, ".github", "workflows", name))
    assert network_gaps(doc, job) == []


def test_every_job_is_scanned():
    """The floor: the three workflows' jobs, the four the coverage measurement runs included."""
    assert len(EVERY_JOB) >= 5 and ("ci.yml", "coverage") in EVERY_JOB, EVERY_JOB


def test_the_retry_runs_a_failing_command_once_more_and_names_it(tmp_path):
    """`scripts/nmas-retry`: a command that fails once then passes ends 0 with one warning; one
    that fails twice ends with the second exit code and an error naming both; one that passes
    runs once and prints nothing."""
    import subprocess
    import sys
    retry = os.path.join(ROOT, "scripts", "nmas-retry")
    count = tmp_path / "count"
    flaky = (f"{sys.executable} -c \"import pathlib,sys; p=pathlib.Path({str(count)!r}); "
             "n=int(p.read_text() or 0) if p.exists() else 0; p.write_text(str(n+1)); "
             "sys.exit(0 if n else 3)\"")
    env = dict(os.environ, NMAS_RETRY_WAIT="0")
    got = subprocess.run([retry, "bash", "-c", flaky], capture_output=True, text=True, env=env)
    assert got.returncode == 0 and count.read_text() == "2", (got.returncode, got.stdout)
    assert "::warning::nmas-retry:" in got.stdout and "(exit 3)" in got.stdout, got.stdout
    got = subprocess.run([retry, "bash", "-c", "exit 4"], capture_output=True, text=True, env=env)
    assert got.returncode == 4 and "failed twice (exit 4, then 4)" in got.stdout, got.stdout
    count.unlink()
    got = subprocess.run([retry, "bash", "-c", flaky.replace("0 if n else 3", "0")],
                         capture_output=True, text=True, env=env)
    assert (got.returncode, got.stdout, count.read_text()) == (0, "", "1")
    got = subprocess.run([retry], capture_output=True, text=True, env=env)
    assert got.returncode == 2 and "usage" in got.stderr


def test_a_planted_unbounded_or_uncached_network_step_is_named():
    """Controls: the promtool download made to run always, the PostgreSQL download unbounded,
    a new apt step with neither, and pip's install unbounded: each named; and a cache nothing
    downloads for."""
    doc, _ = _load(os.path.join(ROOT, ".github", "workflows", "ci.yml"))
    steps = doc["jobs"]["test"]["steps"]
    promtool = next(s for s in steps if str(s.get("name", "")).startswith("promtool for"))
    pg = next(s for s in steps if str(s.get("name", "")).startswith("PostgreSQL 18's packages "
                                                                      "from PGDG"))
    del promtool["if"]
    pg["timeout-minutes"] = 26
    steps.insert(steps.index(pg), {"name": "A new tool", "run": "sudo apt-get install -y x"})
    steps.insert(0, {"name": "An idle cache", "id": "idle", "uses": "actions/cache@v4"})
    install = next(s for s in steps if str(s.get("name", "")).startswith("Install"))
    install.pop("timeout-minutes", None)
    install["run"] += "\npython -m pip install --no-deps -r requirements-extra.txt\n"
    gaps = network_gaps(doc, "test")
    assert any("requirements-extra.txt' reaches the network with no retry" in g
               for g in gaps), gaps
    assert any(g.startswith("Install") and "pip install" in g for g in gaps), gaps
    assert any(g.startswith("promtool for") and "every run" in g for g in gaps), gaps
    assert any(g.startswith("PostgreSQL 18's packages") and "26" in g for g in gaps), gaps
    assert any(g.startswith("A new tool:") for g in gaps), gaps
    assert "cache idle: no step downloads on its miss" in gaps
