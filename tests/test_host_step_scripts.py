"""The operator's host-step scripts (scripts/host-steps/, the operator's request 2026-10-08): one
per section, each running its commands then its checks, stopping at the first failure with what
it wanted and got, and ending with a PASS/FAIL summary of every planned check.

The library runs for real in a temporary folder (no host is touched); each script is parsed for
its shape: it sources the library, declares a plan, names in it every check it makes, and ends
with the summary. minio-4c.sh reads its secret hidden, never from an argument, and never prints
it.
"""

import os
import re
import shutil
import subprocess

import pytest

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "scripts", "host-steps")
# What the repository holds (C585), never what is on disk.
SCRIPTS = sorted(os.path.basename(p) for p in tracked("scripts/host-steps", suffix=".sh")
                 if not p.endswith("lib.sh"))
# The sections the operator named, each a script.
EXPECTED = {"phase3-step1.sh", "phase3-step2.sh", "phase3-step3.sh", "c584-loki-writer.sh",
            "minio-4a-4b.sh", "minio-4c.sh", "minio-lifecycle-probe.sh"}
# minio-4d-4e.sh (pip into the app's interpreter) was removed on 2026-10-08: the operator
# decided on boto3, the host's apt package, so nothing is installed and the lock is
# regenerated from the host, read-only, once the release importing it is deployed.


def _run_planted(tmp_path, body):
    folder = tmp_path / "scripts" / "host-steps"
    folder.mkdir(parents=True)
    shutil.copy(os.path.join(FOLDER, "lib.sh"), folder / "lib.sh")
    script = folder / "planted.sh"
    script.write_text('. "$(dirname "$0")/lib.sh"\n' + body)
    return subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=30)


def test_every_section_has_its_script():
    assert set(SCRIPTS) == EXPECTED


def test_a_failed_check_stops_and_the_summary_names_every_check(tmp_path):
    got = _run_planted(tmp_path, """
plan "one" "two" "three"
check "one" eq "a" 'echo a'
check "two" eq "b" 'echo nope'
check "three" eq "c" 'echo c'
summary
""")
    assert got.returncode == 1, got.stdout
    out = got.stdout
    assert "FAIL  two" in out and "wanted (eq): b" in out and "got (exit 0): nope" in out
    assert re.search(r"PASS\s+one\n\s+FAIL\s+two\n\s+NOT RUN\s+three", out), out
    assert "== RESULT: FAIL at: two" in out
    assert "PASS  three" not in out, "it stopped at the first failure"


def test_a_failed_step_stops_before_the_checks(tmp_path):
    got = _run_planted(tmp_path, """
plan "after"
step "a step that fails" 'false'
check "after" eq "x" 'echo x'
summary
""")
    assert got.returncode == 1
    assert "STEP FAILED: a step that fails" in got.stdout and "NOT RUN  after" in got.stdout


def test_all_passing_ends_pass(tmp_path):
    got = _run_planted(tmp_path, """
plan "one" "two"
check "one" ge 2 'echo 3'
check "two" lacks "secret" 'echo fine'
summary
""")
    assert got.returncode == 0 and "== RESULT: PASS (2 of 2 checks)" in got.stdout


def test_a_held_secret_is_masked_in_what_is_printed(tmp_path):
    got = _run_planted(tmp_path, """
plan "leaks"
REDACT="s3cr3t-value-123"
export X="s3cr3t-value-123"
check "leaks" eq "other" 'echo "$X"'
""")
    assert "s3cr3t-value-123" not in got.stdout + got.stderr
    assert "<redacted>" in got.stdout


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_script_sources_the_library_plans_every_check_and_summarises(name):
    text = open(os.path.join(FOLDER, name), encoding="utf-8").read()
    assert '. "$(dirname "$0")/lib.sh"' in text
    plan = re.search(r"^plan ((?:\"[^\"]+\"\s*\\?\s*)+)", text, re.M)
    assert plan, f"{name} declares no plan"
    planned = re.findall(r'"([^"]+)"', plan.group(1))
    checked = re.findall(r'^check "([^"]+)"', text, re.M)
    stops = re.findall(r'_stop "([^"]+)"', text)
    if "not_root" in text:
        checked.append("run as the operator's own user, not root")
    assert checked, f"{name} makes no check"
    assert not set(checked + stops) - set(planned), f"{name}: checks missing from its plan"
    assert not set(planned) - set(checked), f"{name}: planned checks it never makes"
    assert text.rstrip().endswith("summary"), f"{name} does not end with its summary"
    assert os.access(os.path.join(FOLDER, name), os.X_OK)


def test_the_secret_is_prompted_hidden_never_an_argument_never_printed():
    text = open(os.path.join(FOLDER, "minio-4c.sh"), encoding="utf-8").read()
    assert re.search(r'read -r -s -p "[^"]*" SECRET', text), "prompted, input hidden"
    assert not re.search(r"\$[1-9@*]", text), "no argument is read"
    assert not re.search(r'echo[^\n]*\$\{?SECRET', text), "never echoed"
    assert 'REDACT=$SECRET' in text, "masked in anything a check prints"
    # It reaches mc on standard input or in the environment, never on a command line.
    assert "printf '%s\\n%s\\n' mercury \"$SECRET\" | mc admin user add lab" in text
    assert not re.search(r"mc [^\n|]*\$\{?SECRET", text)
