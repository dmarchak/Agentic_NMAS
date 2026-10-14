"""`scripts/nmas-test` runs CI's interpreter, or refuses and names it (the operator, 2026-10-14).

From an ordinary terminal the runner took `python3` from PATH, which on the operator's laptop is
3.14, and ran the suite there without a word while the gate and CI run 3.12.3. Now, with no
`PYTHON` given, it runs CI's environment (`~/.local/share/nmas-py312`, built by
`scripts/nmas-ci-env`); without one, `python3` only when it is the version `ci.yml` pins; and
otherwise it refuses, naming both versions and the command that builds the right one. A
`PYTHON` given is honoured (the gate and `nmas-deploy` pass theirs) and said when it is not CI's.

Each case runs the REAL script with stand-in interpreters that report a chosen version and say
when pytest was asked for. CI's version is read here from `ci.yml` as YAML, a path independent
of the script's own reading.
"""

import os
import subprocess

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-test")


def _ci_version() -> str:
    with open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8") as fh:
        wf = yaml.safe_load(fh)
    versions = {str(step["with"]["python-version"]) for job in wf["jobs"].values()
                for step in job["steps"] if "python-version" in (step.get("with") or {})}
    assert len(versions) == 1, versions
    return versions.pop()


CI = _ci_version()


def _fake_python(path, version):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\n"
                 'case "$*" in\n'
                 f'  *platform*) echo "{version}" ;;\n'
                 '  *"-m pytest"*) echo "STAND-IN PYTEST RAN" ;;\n'
                 "esac\n")
    os.chmod(path, 0o755)
    return path


def _run(tmp_path, *, python3=None, venv=None, given=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    if python3:
        _fake_python(str(bin_dir / "python3"), python3)
    if venv:
        _fake_python(str(home / ".local" / "share" / "nmas-py312" / "bin" / "python"), venv)
    env = dict(os.environ, HOME=str(home), PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    for k in ("PYTHON", "PYTEST_XDIST_WORKER", "NMAS_TEST_INFLIGHT"):
        env.pop(k, None)
    if given:
        env["PYTHON"] = _fake_python(str(tmp_path / "given" / "python"), given)
    return subprocess.run([SCRIPT, "--allow-unconfined", "-q"], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=60)


def test_cis_environment_is_the_default(tmp_path):
    out = _run(tmp_path, python3="3.14.4", venv=CI)
    venv = os.path.join(str(tmp_path), "home", ".local", "share", "nmas-py312", "bin", "python")
    assert out.returncode == 0, out.stderr
    assert f"nmas-test: python: {venv} ({CI}, CI's environment" in out.stdout, out.stdout
    assert "STAND-IN PYTEST RAN" in out.stdout


def test_another_python3_is_refused_naming_both_versions_and_the_fix(tmp_path):
    out = _run(tmp_path, python3="3.14.4")
    assert out.returncode == 2, (out.returncode, out.stdout, out.stderr)
    assert "STAND-IN PYTEST RAN" not in out.stdout
    assert "nmas-test: REFUSED:" in out.stderr
    assert "Python 3.14.4" in out.stderr and f"CI runs {CI}" in out.stderr, out.stderr
    assert "scripts/nmas-ci-env" in out.stderr and "PYTHON=" in out.stderr


def test_a_python3_of_cis_version_runs(tmp_path):
    out = _run(tmp_path, python3=CI)
    assert out.returncode == 0, out.stderr
    assert f"nmas-test: python: python3 ({CI}, python3 on PATH" in out.stdout, out.stdout
    assert "STAND-IN PYTEST RAN" in out.stdout


def test_a_python_given_is_honoured_and_said_when_it_is_not_cis(tmp_path):
    out = _run(tmp_path, python3=CI, venv=CI, given="3.14.4")
    given = os.path.join(str(tmp_path), "given", "python")
    assert out.returncode == 0, out.stderr
    assert f"nmas-test: python: {given} (3.14.4, PYTHON; not CI's {CI})" in out.stdout, \
        out.stdout
    assert "STAND-IN PYTEST RAN" in out.stdout
