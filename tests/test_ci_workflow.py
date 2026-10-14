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


@pytest.mark.parametrize("path", WORKFLOWS)
def test_the_token_is_read_only(path):
    doc, _ = _load(path)
    assert doc.get("permissions") == {"contents": "read"}, doc.get("permissions")
    for job in (doc.get("jobs") or {}).values():
        assert job.get("permissions") in (None, {"contents": "read"}), job.get("permissions")


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
def test_superseded_runs_are_cancelled_except_on_main_and_docs_are_skipped(path):
    """C440 (the operator, 2026-10-04): a run on main is never cancelled, since the Update
    button needs every commit's verdict (C436); a run on any other ref still is."""
    doc, _ = _load(path)
    assert (doc.get("concurrency") or {}).get("cancel-in-progress") == \
        "${{ github.ref != 'refs/heads/main' }}"
    triggers = doc.get(True) or doc.get("on")      # YAML 1.1 reads `on` as True
    assert "docs/**" in (triggers.get("push") or {}).get("paths-ignore", [])


@pytest.mark.parametrize("path", SUITE_WORKFLOWS)
def test_the_suite_runs_confined_and_never_unconfined(path):
    """C46: CI runs the suite through scripts/nmas-test, which requires the
    network namespace it creates. Parsed values, not the raw text."""
    doc, _ = _load(path)
    runs = [str(s.get("run", "")) for s in _steps(doc)]
    suite = [r for r in runs if "pytest" in r or "nmas-test" in r]
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

    def test_the_nights_tests_stand_on_cis_setup_step_for_step(self):
        ci, night = self._docs()
        ci_steps, n_steps = ci["jobs"]["test"]["steps"], night["jobs"]["test"]["steps"]
        before = ci_steps[:ci_steps.index(_tests_step(ci))]
        runs = {s["run"] for s in n_steps if "run" in s}
        missing = [s.get("name") for s in before if "run" in s and s["run"] not in runs]
        assert len([s for s in before if "run" in s]) >= 7 and missing == [], missing   # 7 today
        assert night["jobs"]["test"]["strategy"] == ci["jobs"]["test"]["strategy"]

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
