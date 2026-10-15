"""C788's host steps (scripts/host-steps/c788-loki-writer-rotate.sh and its undo): MinIO's
loki-writer key moved out of Loki's storage URL into a root-only env file, rotated to a secret
generated on the host, with a backup and an undo.

The step's helper (its `keys.py` heredoc) RUNS here against Loki's configuration as the NMAS host
holds it (tests/fixtures/loki/local-config.masked.yaml: read 2026-10-15 through scripts/nmas-host,
which printed its userinfo masked; the address replaced by a documentation one, the userinfo
planted here at run time so no credential-shaped string is committed). The shell around it is
held by its shape: the new secret never reaches a command line or the output, the undo is armed
before MinIO's secret changes and disarmed only once the old key is refused, and the container
is recreated exactly as it was measured, run for real with a recording `sudo`.
"""

import ast
import json
import os
import re
import socket
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "scripts", "host-steps")
ROTATE = os.path.join(FOLDER, "c788-loki-writer-rotate.sh")
UNDO = os.path.join(FOLDER, "c788-loki-writer-undo.sh")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "loki", "local-config.masked.yaml")
OLD = "PLANTED-old-key-7q"
NEW = "PLANTED-new-key-3x"


def _text(path=ROTATE):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _heredoc(tag: str, start: str) -> str:
    m = re.search(re.escape(start) + r" <<'?%s'?\n(.*?)\n%s\n" % (tag, tag), _text(), re.S)
    assert m, f"no {start} heredoc"
    return m.group(1) + "\n"


def _keys(tmp_path):
    path = tmp_path / "keys.py"
    path.write_text(_heredoc("PY", 'cat > "$DIR/keys.py"'))
    return path


def _copy(tmp_path, userinfo=f"loki-writer:{OLD}"):
    """The dated copy as the step makes it: the host's configuration with its key in the URL."""
    text = open(FIXTURE, encoding="utf-8").read()
    assert text.count("http://***@") == 1, "the fixture is the masked capture"
    path = tmp_path / "local-config.yaml"
    path.write_text(text.replace("http://***@", f"http://{userinfo}@"))
    return path


def _run(keys, *args, stdin=""):
    got = subprocess.run([sys.executable, str(keys), *map(str, args)], input=stdin,
                         capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr
    return got.stdout


class TestTheHelperReadsTheOldUrl:
    def test_endpoint_bucket_and_user_never_the_secret(self, tmp_path):
        keys, copy = _keys(tmp_path), _copy(tmp_path)
        assert _run(keys, "endpoint", copy) == "192.0.2.11:9000\n"
        assert _run(keys, "bucket", copy) == "loki\n"
        assert _run(keys, "user", copy) == "loki-writer\n"
        for what in ("endpoint", "bucket", "user"):
            assert OLD not in _run(keys, what, copy)

    def test_the_old_key_reaches_only_mcs_standard_input_shape(self, tmp_path):
        assert _run(_keys(tmp_path), "old-to-mc", _copy(tmp_path)) == f"loki-writer\n{OLD}\n"

    def test_a_percent_encoded_secret_is_decoded(self, tmp_path):
        copy = _copy(tmp_path, userinfo="loki-writer:a%2Fb%40c")
        assert _run(_keys(tmp_path), "old-to-mc", copy) == "loki-writer\na/b@c\n"

    def test_differs_compares_with_the_old(self, tmp_path):
        keys, copy = _keys(tmp_path), _copy(tmp_path)
        assert _run(keys, "differs", copy, stdin=OLD) == "SAME\n"
        assert _run(keys, "differs", copy, stdin=NEW) == "differs\n"

    def test_two_s3_urls_are_refused_never_guessed(self, tmp_path):
        copy = _copy(tmp_path)
        copy.write_text(copy.read_text() + "  other:\n    s3: http://x@192.0.2.12:9000/b\n")
        got = subprocess.run([sys.executable, str(_keys(tmp_path)), "endpoint", str(copy)],
                             capture_output=True, text=True, timeout=60)
        assert got.returncode != 0 and "2 s3: URLs" in got.stderr


class TestTheRewrite:
    def _rewritten(self, tmp_path):
        keys, copy = _keys(tmp_path), _copy(tmp_path)
        out = tmp_path / "new.yaml"
        _run(keys, "rewrite", copy, out)
        return keys, copy, out

    def test_the_storage_block_holds_the_keys_by_reference(self, tmp_path):
        _keys_, _copy_, out = self._rewritten(tmp_path)
        aws = yaml.safe_load(out.read_text())["storage_config"]["aws"]
        assert aws == {"endpoint": "192.0.2.11:9000", "bucketnames": "loki",
                       "access_key_id": "${LOKI_S3_ACCESS_KEY_ID}",
                       "secret_access_key": "${LOKI_S3_SECRET_ACCESS_KEY}",
                       "s3forcepathstyle": True, "insecure": True}
        assert OLD not in out.read_text() and "://" not in re.search(
            r"storage_config:\n(.*?)\n\S", out.read_text(), re.S).group(1)

    def test_nothing_else_changes(self, tmp_path):
        _keys_, copy, out = self._rewritten(tmp_path)
        before, after = yaml.safe_load(copy.read_text()), yaml.safe_load(out.read_text())
        before["storage_config"]["aws"].pop("s3")
        for k in ("endpoint", "bucketnames", "access_key_id", "secret_access_key"):
            after["storage_config"]["aws"].pop(k)
        assert before == after
        old_lines, new_lines = copy.read_text().splitlines(), out.read_text().splitlines()
        assert len(set(old_lines) - set(new_lines)) == 1 and len(new_lines) == len(old_lines) + 3

    def test_clean_passes_the_rewrite_and_fails_the_original(self, tmp_path):
        keys, copy, out = self._rewritten(tmp_path)
        assert _run(keys, "clean", copy, out, stdin=NEW) == "clean\n"
        got = _run(keys, "clean", copy, copy, stdin=NEW)
        assert got.startswith("FOUND: ") and "a URL with userinfo" in got and "the old secret" in got
        out.write_text(out.read_text() + f"# {NEW}\n")
        assert "the new secret" in _run(keys, "clean", copy, out, stdin=NEW)


class TestNoSecretInTheOutput:
    def test_absent_finds_either_secret_and_a_url_with_userinfo(self, tmp_path):
        keys, copy = _keys(tmp_path), _copy(tmp_path)
        live = tmp_path / "live.yaml"
        _run(keys, "rewrite", copy, live)
        log = tmp_path / "out.log"
        log.write_text("PASS  Loki ready\nnmas: via LAN\nthe storage http://***@192.0.2.11 masked\n")
        assert _run(keys, "absent", copy, log, live, stdin=NEW) == "absent\n"
        for planted, word in ((NEW, "the new secret in the output"),
                              (OLD, "the old secret in the output"),
                              (f"s3://u:{OLD}x@h", "a URL with userinfo in the output")):
            log.write_text(f"got: {planted}\n")
            assert word in _run(keys, "absent", copy, log, live, stdin=NEW)


class TestTheOldKeyIsRefusedOnlyWhenMinioSaysSo:
    def test_an_unreachable_minio_is_unreadable_never_refused(self, tmp_path):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        copy = _copy(tmp_path)
        copy.write_text(copy.read_text().replace("192.0.2.11:9000", f"127.0.0.1:{port}"))
        got = _run(_keys(tmp_path), "old-refused", copy)
        assert got.startswith("UNREADABLE (") and not got.startswith("refused")

    def test_refused_names_only_minios_own_refusals(self):
        refused = re.search(r"^REFUSED = (\{.*\})$", _heredoc("PY", 'cat > "$DIR/keys.py"'), re.M)
        assert refused and ast.literal_eval(refused.group(1)) == {
            "SignatureDoesNotMatch", "InvalidAccessKeyId", "AccessDenied"}


class TestTheTrace:
    """A PLANTED trace in the shape of `mc admin trace -v` as mc's source writes it (each line
    prefixed by the node; a `[REQUEST <call>]` line opens a request, `[RESPONSE]` its answer),
    not a capture: the operator's run is the first real one, and its check is read only after
    the undo is disarmed, so a misreading fails the run without undoing a working rotation."""

    BLOCK = ("192.0.2.11:9000 [REQUEST {call}] [2026-10-15T01:20:00.000] [Client IP: 192.0.2.30]\n"
             "192.0.2.11:9000 {method} /{bucket}/fake/abc\n"
             "192.0.2.11:9000 Authorization: AWS4-HMAC-SHA256 Credential={who}/20261015/us-east-1/"
             "s3/aws4_request, SignedHeaders=host, Signature=00\n"
             "192.0.2.11:9000 [RESPONSE] [2026-10-15T01:20:00.002] [ Duration 2ms ]\n"
             "192.0.2.11:9000 {status}\n\n")

    def _trace(self, tmp_path, *blocks):
        path = tmp_path / "trace.txt"
        path.write_text("".join(self.BLOCK.format(**b) for b in blocks))
        return _run(_keys(tmp_path), "trace", path, "loki").strip()

    def test_counts_loki_puts_their_signers_and_refusals(self, tmp_path):
        put = {"call": "s3.PutObject", "method": "PUT", "bucket": "loki", "who": "loki-writer",
               "status": "200 OK"}
        assert self._trace(tmp_path, put, put) == "puts=2 signers=loki-writer refused=0"
        assert self._trace(tmp_path, put, {**put, "status": "403 Forbidden"}) == \
            "puts=2 signers=loki-writer refused=1"
        assert self._trace(tmp_path, put, {**put, "who": "minioadmin"}) == \
            "puts=2 signers=loki-writer,minioadmin refused=0"

    def test_other_buckets_and_calls_are_not_lokis_writes(self, tmp_path):
        put = {"call": "s3.PutObject", "method": "PUT", "bucket": "loki", "who": "loki-writer",
               "status": "200 OK"}
        assert self._trace(tmp_path, {**put, "bucket": "thanos", "who": "thanos"},
                           {**put, "call": "s3.ListObjectsV2", "method": "GET",
                            "status": "403 Forbidden"}) == "puts=0 signers=- refused=0"

    def test_colour_codes_are_ignored(self, tmp_path):
        path = tmp_path / "trace.txt"
        path.write_text(self.BLOCK.format(call="s3.PutObject", method="PUT", bucket="loki",
                                          who="loki-writer", status="200 OK")
                        .replace("[REQUEST", "\x1b[32m[REQUEST").replace("200 OK", "\x1b[1m200 OK"))
        assert _run(_keys(tmp_path), "trace", path, "loki").strip() == \
            "puts=1 signers=loki-writer refused=0"


class TestTheShellAroundIt:
    def test_the_new_secret_is_generated_and_never_on_a_command_line(self):
        text = _text()
        assert "NEW_SECRET=$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 40)" in text
        assert "REDACT=$NEW_SECRET" in text
        assert not re.search(r"echo[^\n]*\$\{?NEW_SECRET", text), "never echoed"
        # Within one command (never past | & ;): printf is a builtin, never in the process list.
        assert not re.search(
            r'(?:\bmc\b|python3|"\$PY"|\bgrep\b|\bsudo\b|\bcurl\b|\bdocker\b)[^\n|&;]*\$\{?NEW_SECRET',
            text), "the new secret an argument"
        assert len(re.findall(r'printf "[^"]*" "\$NEW_SECRET" \|', text)) >= 6

    def test_the_root_password_is_read_hidden_and_reaches_python_on_stdin(self):
        for path in (ROTATE, UNDO):
            text = _text(path)
            assert re.search(r'read -r -s -p "[^"]*\(hidden\): " ROOT_PW', text), path
            assert "MC_HOST_lokiadm=$(printf '%s' \"$ROOT_PW\" | " in text, path
            assert text.count("$ROOT_PW") == 1 and "unset ROOT_PW" in text, path

    def test_the_undo_is_armed_before_the_secret_changes_and_disarmed_after_the_old_is_refused(self):
        text = _text()
        armed = text.index("\nON_FAIL=undo\n")
        change = text.index('printf "loki-writer\\n%s\\n" "$NEW_SECRET" | mc admin user add lokiadm')
        refused = text.index('check "the old key is refused"')
        disarmed = text.index('\nON_FAIL=""\n')
        trace = text.index('check "the trace: ')
        assert armed < change < refused < disarmed < trace
        undo = re.search(r"^undo\(\) \{\n(.*?)^\}", text, re.S | re.M).group(1)
        for part in ("old-to-mc", 'install -m 640 -o root -g 10001 "$COPY/local-config.yaml" "$CONFIG"',
                     'rm -f "$ENVFILE"', "recreate before"):
            assert part in undo, part

    def test_the_policy_is_c584s(self):
        mine = json.loads(_heredoc("JSON", 'cat > "$DIR/loki-only.json"'))
        c584 = open(os.path.join(FOLDER, "c584-loki-writer.sh"), encoding="utf-8").read()
        theirs = json.loads(re.search(r"<<'JSON'\n(.*?)\nJSON\n", c584, re.S).group(1))
        assert mine == theirs

    def _recreated(self, tmp_path, path, call):
        """The `docker run` argv the script's recreate makes, through a `sudo` that records."""
        fake = tmp_path / "bin"
        fake.mkdir(exist_ok=True)
        rec = tmp_path / "argv.txt"
        (fake / "sudo").write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> {rec}\necho >> {rec}\n')
        (fake / "sudo").chmod(0o755)
        fn = re.search(r"^recreate\(\) \{\n.*?^\}\n", _text(path), re.S | re.M).group(0)
        rec.write_text("")
        subprocess.run(["bash", "-c", fn + call], check=True, timeout=30,
                       env={"PATH": f"{fake}:/usr/bin:/bin", "IMAGE": "grafana/loki:3.3.2",
                            "ENVFILE": "/etc/loki/loki-s3.env"})
        runs = [c.split("\n") for c in rec.read_text().split("\n\n") if c.startswith("docker\nrun")]
        assert len(runs) == 1
        return runs[0]

    def _measured(self, path):
        m = re.search(r'check "the running Loki container is the one [^"]*" eq "([^"]*)"', _text(path))
        return m.group(1).split()

    def test_recreate_before_is_the_container_as_measured(self, tmp_path):
        for path, call in ((ROTATE, "recreate before"), (UNDO, "recreate")):
            argv = self._recreated(tmp_path, path, call)
            image, args, port, bind1, bind2, restart = self._measured(path)[:6]
            assert argv[argv.index("--restart") + 1] == restart
            assert argv[argv.index("-p") + 1] == f"{port}:{port}"
            assert [argv[i + 1] for i, a in enumerate(argv) if a == "-v"] == [bind1, bind2]
            assert argv[argv.index(image) + 1:] == [args.strip("[]")]
            assert "--env-file" not in argv

    def test_recreate_after_adds_only_the_env_file_and_expansion(self, tmp_path):
        before = self._recreated(tmp_path, ROTATE, "recreate before")
        after = self._recreated(tmp_path, ROTATE, "recreate after")
        extra = [a for a in after if a not in before]
        assert extra == ["--env-file", "/etc/loki/loki-s3.env", "-config.expand-env=true"]
        assert after.index("--env-file") < after.index("grafana/loki:3.3.2") < \
            after.index("-config.expand-env=true")

    def test_the_rotation_and_its_undo_measure_the_same_container(self):
        assert self._measured(ROTATE) == self._measured(UNDO)
