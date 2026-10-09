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
            "minio-4a-4b.sh", "minio-4c.sh", "minio-lifecycle-probe.sh", "postgres-6a.sh",
            "venv-1-build.sh", "venv-2-switch.sh", "venv-3-undo.sh", "venv-swap.sh",
            "venv-rollback.sh", "postgres-rotate.sh"}
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


def test_on_fail_undoes_before_the_summary_and_the_result_stays_fail(tmp_path):
    """Section 8.3: the venv swap points its link back when a proof fails."""
    got = _run_planted(tmp_path, """
plan "one" "two"
ON_FAIL='echo UNDONE'
ON_FAIL_WHAT="point the link back"
check "one" eq "a" 'echo a'
check "two" eq "b" 'echo nope'
summary
""")
    out = got.stdout
    assert got.returncode == 1
    assert "== ON FAILURE: point the link back" in out and "UNDONE" in out
    assert out.index("UNDONE") < out.index("== SUMMARY") and "== RESULT: FAIL at: two" in out


def test_on_fail_never_runs_when_everything_passes(tmp_path):
    got = _run_planted(tmp_path, """
plan "one"
ON_FAIL='echo UNDONE'
check "one" eq "a" 'echo a'
summary
""")
    assert got.returncode == 0 and "UNDONE" not in got.stdout


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


def test_the_rotation_sends_the_server_a_verifier_never_the_password():
    """postgres-rotate.sh (board F2's rotation order, the server first): the new password is
    read hidden, masked, never an argument or echoed; the server is sent a SCRAM-SHA-256
    verifier on psql's standard input, so the password is in no statement log; the env file's
    copy is replaced on install's standard input."""
    text = open(os.path.join(FOLDER, "postgres-rotate.sh"), encoding="utf-8").read()
    assert re.search(r'read -r -s -p "[^"]*" PW', text), "prompted, input hidden"
    assert not re.search(r"\$[1-9@*]", text), "no argument is read"
    assert not re.search(r'echo[^\n]*\$\{?PW\b', text), "never echoed"
    assert "REDACT=$PW" in text
    assert "VERIFIER=$(printf '%s' \"$PW\" | python3 -c \"$SCRAM\")" in text
    assert "| docker exec -i mercury-postgres psql" in text and "\"$VERIFIER\"" in text
    assert not re.search(r"ALTER ROLE[^\n]*\$PW", text), "the password never reaches SQL"
    assert '| sudo install -m 0600 /dev/stdin "$ENV_FILE"' in text
    # The verifier verifies the password by RFC 7677's own arithmetic (an independent path:
    # recomputed here from the password and the verifier's salt, not by the script's code).
    import base64
    import hashlib
    import hmac

    scram = re.search(r"^SCRAM='(.*?)'$", text, re.S | re.M).group(1)
    pw = "rotated-Password_123.abcdefghij"
    out = subprocess.run(["python3", "-c", scram], input=pw, capture_output=True, text=True,
                         check=True).stdout.strip()
    m = re.fullmatch(r"SCRAM-SHA-256\$(\d+):([^$]+)\$([^:]+):(.+)", out)
    assert m, out
    it, salt = int(m.group(1)), base64.b64decode(m.group(2))
    salted = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, it)
    stored = hashlib.sha256(hmac.new(salted, b"Client Key", hashlib.sha256).digest()).digest()
    server = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    assert (base64.b64decode(m.group(3)), base64.b64decode(m.group(4))) == (stored, server)
    assert it == 4096 and len(salt) == 16


def test_the_records_password_is_prompted_hidden_and_reaches_only_stdin_and_the_environment():
    """postgres-6a.sh: Mercury's database password is read hidden, masked in what a check
    prints, and reaches the env file on install's standard input and psycopg through the
    environment, never a command line; the superuser's is generated and never shown."""
    text = open(os.path.join(FOLDER, "postgres-6a.sh"), encoding="utf-8").read()
    assert re.search(r'read -r -s -p "[^"]*" PW', text), "prompted, input hidden"
    assert not re.search(r"\$[1-9@*]", text), "no argument is read"
    assert not re.search(r'echo[^\n]*\$\{?PW\b', text), "never echoed"
    assert "REDACT=$PW" in text, "masked in anything a check prints"
    assert '| sudo install -m 0600 /dev/stdin "$DIR/postgres.env"' in text
    assert 'password=os.environ[\\"PW\\"]' in text
    assert "$(openssl rand -hex 24)" in text and not re.search(r"echo[^\n]*POSTGRES_PASSWORD", text)
    # The init folder is readable by the image's own user (postgres, uid 70): installed 0750
    # root-only on 2026-10-09, the entrypoint could not list it and the container restarted
    # eleven times. 6a proves it by that user, in that image, before it starts the container.
    assert 'sudo install -d -m 0755 "$DIR/initdb"' in text and 'sudo chmod 0755 "$DIR/initdb"' in text
    assert re.search(r'docker run --rm --entrypoint ls -u postgres -v "\$DIR/initdb:'
                     r'/docker-entrypoint-initdb.d:ro" "\$IMAGE"', text)
    assert text.index("reads the init folder as installed\" has") < text.index("up -d --force-recreate")
    # The compose file publishes the port on loopback only, and pins the image by digest.
    compose = open(os.path.join(ROOT, "deploy", "postgres", "docker-compose.yml"),
                   encoding="utf-8").read()
    assert '- "127.0.0.1:5433:5432"' in compose
    assert re.search(r"image: postgres:18-alpine@sha256:[0-9a-f]{64}\n", compose)
