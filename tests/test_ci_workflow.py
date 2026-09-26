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

import glob
import os

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOWS = sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.y*ml")))


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh), fh.name


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
    """Floor: an empty glob would pass every test below."""
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
    assert not [t for t in strings if "rcn-nsot-config" in t]
    for key, _value in _walk(doc):
        assert key not in ("repository", "token", "ssh-key"), key
    for step in _steps(doc):
        if str(step.get("uses", "")).startswith("actions/checkout"):
            assert (step.get("with") or {}).get("persist-credentials") is False, step


@pytest.mark.parametrize("path", WORKFLOWS)
def test_it_installs_the_hosts_versions_and_never_gates_on_coverage(path):
    raw = open(path, encoding="utf-8").read()
    assert "pip install --no-deps -r requirements.lock" in raw, \
        "without --no-deps a resolver installs something other than the host's set"
    assert "-r requirements.txt" not in raw, "requirements.txt describes no machine (C37)"
    assert "--cov-fail-under" not in raw and "fail_under" not in raw


@pytest.mark.parametrize("path", WORKFLOWS)
def test_superseded_runs_are_cancelled_and_docs_are_skipped(path):
    doc, _ = _load(path)
    assert (doc.get("concurrency") or {}).get("cancel-in-progress") is True
    triggers = doc.get(True) or doc.get("on")      # YAML 1.1 reads `on` as True
    assert "docs/**" in (triggers.get("push") or {}).get("paths-ignore", [])


@pytest.mark.parametrize("path", WORKFLOWS)
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
