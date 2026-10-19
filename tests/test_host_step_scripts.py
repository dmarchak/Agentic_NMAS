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
EXPECTED = {"phase3-step1.sh", "phase3-step2.sh", "c584-loki-writer.sh",
            "minio-4a-4b.sh", "minio-4c.sh", "minio-lifecycle-probe.sh", "postgres-6a.sh",
            "venv-1-build.sh", "venv-2-switch.sh", "venv-3-undo.sh", "venv-swap.sh",
            "venv-rollback.sh", "postgres-rotate.sh",
            # The Phase 7 operating mode, run on the laptop (the operator, 2026-10-09).
            "phase7-mode-on.sh", "phase7-mode-off.sh",
            # C663 step 2: ratify the excluded VRFs before their default empties (2026-10-11).
            "c663-step2-pin-vrfs.sh",
            # C663 step 3b: the topology renderer renamed for the product (2026-10-11).
            "c663-step3b-topology.sh",
            # C529 step 2: each Kea subnet's reservations file of Mercury's (2026-10-11).
            "c529-step2-reservation-files.sh",
            # C529 step 5: Kea's subnets moved into Mercury's files, once (2026-10-11).
            "c529-step5-subnet-files.sh",
            # Board L: the discovery range's classes and pools on the ZTP segment (2026-10-11).
            "ztp-discovery-range.sh",
            # C665: Device Roles' kinds with the operator's admin token, prompted (2026-10-11).
            "netbox-role-kinds.sh",
            # 7.8: the retired topology service's unit and link removed (2026-10-12).
            "topology-service-removal.sh",
            # C722: a `device` label at Loki's ingest, set by Alloy from the line (2026-10-12).
            "c722-device-label.sh",
            # C725: the config repository's workflow and its pin of Mercury (2026-10-12).
            "c725-config-pipeline.sh",
            # C729: the application key on a disk of its own, outside the VM image (2026-10-13).
            "c729-key-disk.sh",
            # C734: the sealed values in each store, counted read-only (2026-10-13).
            "c734-sealed-store-counts.sh",
            # D15: the AI family's data archived (masked, the key sealed), then deleted (2026-10-13).
            "d15-ai-archive.sh",
            # D16: a removed family's data archived (masked), then deleted by checksum.
            "d16-archive.sh",
            # D16: Oxidized's containers and store retired: archived masked, router.db shredded.
            "d16-oxidized-retire.sh",
            # C743: the two first archive objects deleted, every version, with a typed key.
            "c743-delete-archive-objects.sh",
            # E19: the lease lifetimes: Kea's globals and classes, the management subnet's.
            "e19-dhcp-lifetimes.sh",
            # C749: MinIO's default root replaced; Thanos and archive cleanups on keys of their own.
            "minio-root-rotate.sh", "minio-bind.sh",
            # C788: loki-writer's key rotated and moved out of Loki's storage URL, and its undo.
            "c788-loki-writer-rotate.sh", "c788-loki-writer-undo.sh",
            # IBN decision 7: severity on syslog lines, a stable trap job and trap_oid at ingest.
            "ibn7-severity-trap-label.sh",
            # C789: snmptrapd started at boot, so no trap is the one that activates it.
            "c789-snmptrapd-at-boot.sh",
            # C794: Loki's own detected_level off; severity the one level (2026-10-15).
            "c794-loki-detected-level-off.sh",
            # C730: the golden archive's versions counted, masked or not, read-only (2026-10-15).
            "c730-golden-archive-census.sh",
            # C1346: udp/69 admitted from each relayed ZTP subnet, and recorded (2026-10-19).
            "c1346-ztp-relayed-firewall.sh"}
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


def test_a_check_another_mode_asks_is_not_asked_never_pass(tmp_path):
    """C757: the Oxidized archive run reported its delete-mode checks PASS (each echoed "not
    asked" to itself and matched it), though it deleted nothing. `not_asked` records them NOT
    ASKED, and the result counts them apart from the checks that passed."""
    got = _run_planted(tmp_path, """
plan "asked here" "the other mode's"
check "asked here" eq "a" 'echo a'
not_asked "the other mode's" "the --delete run's"
summary
""")
    assert got.returncode == 0, got.stdout
    out = got.stdout
    assert re.search(r"NOT ASKED\s+the other mode's\n", out), out
    assert not re.search(r"PASS\s+the other mode's", out), out
    assert "== RESULT: PASS (1 of 1 checks asked; 1 not asked in this mode)" in out


def test_no_check_answers_not_asked_to_itself():
    """The class C757 found: a check whose command echoes "not asked" and whose wanted value
    accepts it passes in a mode that never asked it. Every such check is `not_asked` now."""
    for name in SCRIPTS:
        text = open(os.path.join(FOLDER, name), encoding="utf-8").read()
        assert not re.search(r"echo [\"']not asked[\"']", text), name
        assert not re.search(r"\bcheck\s+\"[^\"]*\"\s+\w+\s+\"[^\"]*not asked", text), name


def test_the_oxidized_step_destroys_only_in_its_delete_branch():
    """C757's question: did the archive run delete anything? It could not: the container
    removal, the shredding and the store's removal sit only in the branch `--delete` selects."""
    text = open(os.path.join(FOLDER, "d16-oxidized-retire.sh"), encoding="utf-8").read()
    tail = text[text.index("# Each check is asked only in its own mode"):]
    archive, delete = tail.split("\nelse\n", 1)
    assert archive.startswith("# Each check") and 'if [ "$MODE" = archive ]; then' in archive
    delete = delete.split("\nfi\n", 1)[0]
    for destroy in ("docker rm oxidized", "shred -u", 'rm -rf "$STORE"'):
        assert destroy in delete and destroy not in archive, destroy
    assert text.count("docker rm oxidized") == 1 and text.count('rm -rf "$STORE"') == 1


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
    # A check inside a mode's branch is indented; the other mode's is `not_asked` (C757).
    checked = re.findall(r'^\s*(?:check|not_asked) "([^"]+)"', text, re.M)
    stops = re.findall(r'_stop "([^"]+)"', text)
    if "not_root" in text:
        checked.append("run as the operator's own user, not root")
    assert checked, f"{name} makes no check"
    assert not set(checked + stops) - set(planned), f"{name}: checks missing from its plan"
    assert not set(planned) - set(checked), f"{name}: planned checks it never makes"
    assert text.rstrip().endswith("summary"), f"{name} does not end with its summary"
    assert os.access(os.path.join(FOLDER, name), os.X_OK)


def test_the_delete_key_is_prompted_hidden_and_reaches_only_one_commands_environment():
    """C743's delete step: the MinIO key that may delete is typed hidden, never an argument or
    echoed, masked in what a check prints, and handed to Python only in the environment of the
    command that uses it (`MINIO_SECRET="$SECRET"`), which pops it before anything prints."""
    text = open(os.path.join(FOLDER, "c743-delete-archive-objects.sh"), encoding="utf-8").read()
    assert re.search(r'read -r -s -p "[^"]*" SECRET', text), "prompted, input hidden"
    assert not re.search(r"\$[1-9@*]", text), "no argument is read"
    assert not re.search(r'echo[^\n]*\$\{?SECRET', text), "never echoed"
    assert 'REDACT=$SECRET' in text
    assert re.findall(r'\$\{?SECRET\b', text) == ["$SECRET", "$SECRET", "$SECRET"], \
        "the secret is named only where it is checked, masked and handed over"
    assert 'os.environ.pop("MINIO_SECRET")' in text


def test_the_minio_root_rotation_never_shows_a_secret():
    """C749: the new root password and the two users' secrets are typed hidden, twice, never an
    argument or echoed; they reach mc on its standard input or in MC_HOST_ built from standard
    input, and the two files through set_keys.py's standard input. The cleanup key's policy is
    DeleteObject and DeleteObjectVersion on Mercury's bucket, and nothing else."""
    import json as _json

    text = open(os.path.join(FOLDER, "minio-root-rotate.sh"), encoding="utf-8").read()
    for var, words in (("NEW_PW", "The new root password"),
                       ("THANOS_PW", "The secret for the user thanos"),
                       ("CLEANUP_PW", "The secret for the user mercury-cleanup")):
        assert f'ask {var} "{words}"' in text
        assert not re.search(rf'echo[^\n]*\$\{{?{var}\b', text), f"{var} echoed"
        # Within one command (never past && ; or |): printf is a builtin, never in the process list.
        assert not re.search(rf'(?:\bmc\b|python3|"\$PY")[^\n|&;]*"\${var}"', text), \
            f"{var} an argument"
    assert re.search(r'read -r -s -p "\$2 \(hidden\): " a', text), "prompted, input hidden"
    # The function parameters of `ask` and `policy_of` (C752), never the script's arguments.
    assert not re.search(r"\$[1-9@*]", text.replace('"$2 (hidden)', "").replace(
        'printf -v "$1"', "").replace('mc admin user info lab "$1" --json', "")), \
        "no argument is read"
    policy = re.search(r"mercury-cleanup.json\" <<JSON\n(.*?)\nJSON", text, re.S).group(1)
    doc = _json.loads(policy.replace("$BUCKET", "mercury"))
    [stmt] = doc["Statement"]
    assert sorted(stmt["Action"]) == ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    assert stmt["Resource"] == ["arn:aws:s3:::mercury/*"]


def test_the_minio_root_rotation_removes_only_this_minios_aliases(tmp_path):
    """C752: the first run removed `dr`, an alias of the REPLICA, because its root user is also
    named minioadmin. Only aliases naming this MinIO (its endpoint, or loopback on its port) with
    the old root user are removed; and a policy is attached unless the user's policy FIELD names
    it (grepping the info text matched the user's own name, so mercury-cleanup's was skipped)."""
    import json as _json
    import subprocess
    import sys

    text = open(os.path.join(FOLDER, "minio-root-rotate.sh"), encoding="utf-8").read()
    mine = re.search(r"cat > \"\$DIR/mine.py\" <<'PY'\n(.*?)\nPY\n", text, re.S).group(1)
    (tmp_path / "mine.py").write_text(mine)
    aliases = [{"alias": "lab", "URL": "http://192.0.2.11:9000", "accessKey": "minioadmin"},
               {"alias": "dr", "URL": "http://192.0.2.21:9000", "accessKey": "minioadmin"},
               {"alias": "here", "URL": "http://localhost:9000", "accessKey": "minioadmin"},
               {"alias": "local", "URL": "http://localhost:9000", "accessKey": ""},
               {"alias": "otherport", "URL": "http://192.0.2.11:9100", "accessKey": "minioadmin"}]
    got = subprocess.run([sys.executable, str(tmp_path / "mine.py")],
                         input="\n".join(_json.dumps(a) for a in aliases), text=True,
                         capture_output=True, check=True,
                         env={"ENDPOINT": "192.0.2.11:9000", "OLD_USER": "minioadmin",
                              "PATH": os.environ["PATH"]}).stdout.split()
    assert got == ["lab", "here"]
    assert not re.search(r"user info lab \w[\w-]* \| grep", text), "a policy decided by grep"
    assert text.count('[ "$(policy_of ') == 2


def test_the_minio_bind_step_closes_only_what_it_opens_and_undoes_itself():
    """C749's follow-up: the console on loopback, the API kept on every address (its clients name
    this host's LAN address), ufw's allow for docker0 added BEFORE the denies (ufw matches in
    order), both denies logged, and the undo deletes exactly the rules it added (ufw delete takes
    the rule without its comment), puts the file back and restarts MinIO. No secret is read."""
    text = open(os.path.join(FOLDER, "minio-bind.sh"), encoding="utf-8").read()
    assert "WANT_AFTER='\"--address :9000 --console-address 127.0.0.1:9001\"'" in text
    apply = re.search(r'eval "sudo ufw \$RULE_LOKI" && eval "sudo ufw \$RULE_API" && '
                      r'eval "sudo ufw \$RULE_CONSOLE"', text)
    assert apply, "the allow first, then the two denies"
    assert re.search(r'RULE_API="deny log 9000/tcp ', text)
    assert re.search(r'RULE_CONSOLE="deny log 9001/tcp ', text)
    assert re.search(r'RULE_LOKI="allow in on docker0 from \$DOCKNET to any port 9000 proto tcp ',
                     text)
    undo = re.search(r"^ON_FAIL='(.*)'$", text, re.M).group(1)
    assert 'sudo ufw delete ${r% comment *}' in undo
    assert '"$RULE_CONSOLE" "$RULE_API" "$RULE_LOKI"' in undo
    assert 'sudo cp -p "$COPY/minio" "$ENVFILE"' in undo and "systemctl restart minio" in undo
    assert not re.search(r"read -r -s", text), "this step asks for no secret"
    assert not re.search(r"set_keys|MINIO_ROOT_(USER|PASSWORD)=", text), "no key touched"


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


# --- A command runs in a CHILD shell (C748) -------------------------------------------------

#: `(script, variable)` a step's or check's command names without exporting it first, each with
#: why it is not a bug, or the finding that holds it. Only shrinks.
UNEXPORTED_EXCUSED = {
    ("c729-key-disk.sh", "C729_DEFERRAL_LIFTED"):
        "set by the operator in the step's own environment when lifting the deferral",
}


def unexported(text: str) -> list:
    """``[(line, variable)]``: each `$VAR` a step's or check's single-quoted command names that
    no `export` before that line (or the command itself) provides. The library runs every
    command in `bash -c`, a child that sees only exported variables: the C743 delete step's
    first run read its typed key as empty this way (2026-10-13)."""
    special = {"HOME", "USER", "PATH", "PWD", "SUDO_USER", "IFS", "RANDOM", "UID", "EUID"}
    exported, out = set(), []
    for n, line in enumerate(text.splitlines(), 1):
        for m in re.finditer(r"(?:^|;)\s*export\s+([^;]*)", line):
            exported |= {t.split("=")[0] for t in m.group(1).split() if not t.startswith("-")}
        m = re.match(r"\s*(?:step|check)\s+\"[^\"]*\"\s+(?:\w+\s+\S+\s+)?'(.*)", line)
        if not m:
            continue
        # A value spliced in by the outer shell ('…'"$X"'…') is expanded before the child runs.
        cmd = re.sub(r"'\"\$\{?\w+[^\"]*\"'", "", m.group(1))
        local = set(re.findall(r"\b([A-Za-z_]\w*)=", cmd)) | set(
            re.findall(r"\bfor\s+([A-Za-z_]\w*)\s+in\b", cmd))
        for name in sorted(set(re.findall(r"\$\{?([A-Za-z_]\w*)", cmd))
                           - exported - local - special):
            out.append((n, name))
    return out


def test_every_command_names_only_exported_variables():
    found = {(name, var) for name in SCRIPTS
             for _n, var in unexported(open(os.path.join(FOLDER, name), encoding="utf-8").read())}
    assert found - set(UNEXPORTED_EXCUSED) == set(), sorted(found - set(UNEXPORTED_EXCUSED))
    assert set(UNEXPORTED_EXCUSED) - found == set(), "an excuse with nothing to excuse"


def test_the_scan_finds_the_first_runs_bug():
    """The planted case: the C743 step as first run, its typed key read in a check before it
    was exported."""
    planted = ("read -r -p \"Access key: \" ACCESS\n"
               "check \"a key was typed\" eq \"yes\" '[ -n \"$ACCESS\" ] && echo yes || echo no'\n"
               "export ACCESS\n")
    assert unexported(planted) == [(2, "ACCESS")]
    fixed = planted.splitlines()
    assert unexported("\n".join([fixed[0], fixed[2], fixed[1]])) == []
    spliced = "check \"x\" eq 1 'echo \"pkg='\"$PSYCOPG\"'\"'\n"
    assert unexported(spliced) == []


# --- each mode gives the private folder away before running as the user (C758) ---------------

def mode_lines(text: str, mode: str) -> list:
    """``[(line number, text)]`` of the lines a run in *mode* executes, following the script's
    multi-line `if [ "$MODE" = X ]; then … else … fi` branches (any other multi-line `if` keeps
    both branches; heredoc bodies are skipped)."""
    out, stack, heredoc = [], [], None
    for n, line in enumerate(text.splitlines(), 1):
        if heredoc:
            heredoc = None if line.strip() == heredoc else heredoc
            continue
        m = re.search(r"<<'?(\w+)'?\s*$", line)
        stripped = line.strip()
        cond = re.match(r'if \[ "\$MODE" = (\w+) \]; then$', stripped)
        if cond or (stripped.startswith("if ") and stripped.endswith("then")):
            stack.append([cond.group(1) if cond else None, False])
        elif stripped == "else" and stack:
            stack[-1][1] = True
        elif stripped == "fi" and stack:
            stack.pop()
        elif all(c is None or (c == mode) != in_else for c, in_else in stack):
            out.append((n, line))
        if m:
            heredoc = m.group(1)
    return out


def folder_order(text: str, mode: str):
    """(the first line giving "$DIR" away by chown, the first `sudo -u` line naming "$DIR"), in
    *mode*'s run; None where there is none."""
    lines = mode_lines(text, mode)
    chown = next((n for n, l in lines if re.search(r'\bchown\b[^\']*"\$DIR"', l)), None)
    # The sudo'd command ends at the next quote, `)`, `|`, `;` or `&` (venv-1-build's
    # `diff <(sudo -u … "$LOCK") <("$DIR/…")` names "$DIR" outside it).
    runas = next((n for n, l in lines if re.search(r"\bsudo -u \S+[^')|;&]*\$DIR", l)), None)
    return chown, runas


def test_each_mode_gives_the_folder_away_before_running_as_the_user():
    """C758: the Oxidized step's --delete run could not open archive.py, because its private
    folder (mktemp, root's, 700) was given to the operator's user only in the archive mode's
    copy step. In every mode, a chown of "$DIR" comes before the first `sudo -u` reading it."""
    for name in SCRIPTS:
        text = open(os.path.join(FOLDER, name), encoding="utf-8").read()
        if not re.search(r"\bsudo -u \S+[^')|;&\n]*\$DIR", text):
            continue
        modes = set(re.findall(r'if \[ "\$MODE" = (\w+) \]; then', text)) or {"only"}
        modes |= {"delete"} if "--delete" in text else set()
        for mode in modes:
            chown, runas = folder_order(text, mode)
            if runas is not None:
                assert chown is not None and chown < runas, (name, mode, chown, runas)


def test_the_folder_scan_finds_the_first_delete_runs_bug():
    """The planted case: the step as the first --delete run met it, the chown in the archive
    branch only."""
    planted = ('DIR=$(mktemp -d)\n'
               'if [ "$MODE" = archive ]; then\n'
               '    step "copy" \'cp -a "$STORE" "$DIR/store" && chown -R "$RUNAS" "$DIR"\'\n'
               '    step "build" \'sudo -u "$RUNAS" env DIR="$DIR" "$PY" "$DIR/archive.py"\'\n'
               'else\n'
               '    step "find" \'sudo -u "$RUNAS" env DIR="$DIR" "$PY" "$DIR/archive.py"\'\n'
               'fi\n')
    assert folder_order(planted, "archive") == (3, 4)
    assert folder_order(planted, "delete") == (None, 6)
    fixed = planted.replace("if [", 'step "give" \'chown -R "$RUNAS" "$DIR"\'\nif [', 1)
    assert folder_order(fixed, "delete") == (2, 7)


# --- sudo resets the environment (C755) -------------------------------------------------------

def sudo_env_reads(text: str) -> list:
    """``[line]``: each line where a process started by `sudo` reads the ENVIRONMENT, which sudo
    resets: Python's `os.environ` or `os.getenv` inside a `sudo … python3` command, or a
    `sudo bash -c` / `sudo sh -c` whose script names a `$VAR`. minio-bind.sh's first run on the
    host read its wanted MINIO_OPTS this way (KeyError, 2026-10-13); a value goes in as an
    argument, which sudo passes through."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in re.finditer(r"\bsudo\b(?:\s+-[A-Za-z]+(?:\s+\S+)?)*\s+(\S+)", line):
            prog, cmd = m.group(1), re.split(r"\s(?:&&|\|\||\|)\s", line[m.end():], 1)[0]
            if (re.search(r"python3?$", prog) and re.search(r"os\.environ|os\.getenv", cmd)) or (
                    prog in ("bash", "sh") and re.search(r"-c\s+['\"].*\$\{?[A-Za-z_]", cmd)):
                out.append(n)
    return out


def test_no_process_started_by_sudo_reads_the_environment():
    found = {name: sudo_env_reads(open(os.path.join(FOLDER, name), encoding="utf-8").read())
             for name in SCRIPTS}
    assert {k: v for k, v in found.items() if v} == {}


def test_the_sudo_scan_finds_the_first_runs_bug():
    """The planted case: minio-bind.sh's step as first run on the host."""
    planted = ("step \"x\" \\\n"
               "    'sudo python3 -c \"import os, re, sys; p = sys.argv[1]; t = os.environ[\\\"W\\\"]\" \"$F\"'\n")
    assert sudo_env_reads(planted) == [2]
    assert sudo_env_reads(planted.replace('os.environ[\\"W\\"]', "sys.argv[2]")) == []
    assert sudo_env_reads("    'sudo bash -c \"echo $X\"'\n") == [1]
    assert sudo_env_reads("    'sudo cp -a \"$A\" \"$B\"'\n") == []
