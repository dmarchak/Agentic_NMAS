"""The record that has to survive the routers being unreachable.

Stage B measured what a bad redeploy looks like: five routers up, healthy,
answering SSH, holding a credential nobody has. The way back in is the serial
console on the containerlab host, and it needs the credential that was live
BEFORE the redeploy -- which otherwise exists only inside `devices.csv`,
encrypted with `data/key.key`, on a machine the operator may not be at.

Three properties, each answering a specific way the obvious version fails.
"""

import json
import os
import subprocess
import sys

import pytest

import modules.breakglass as bg

PASS = "a-long-enough-passphrase"
DEVICES = [
    {"hostname": "r1", "ip": "a", "username": "admin", "password": "same",
     "secret": "en1", "platform": "cisco_iosxe"},
    {"hostname": "r2", "ip": "b", "username": "admin", "password": "same",
     "platform": "cisco_iosxe"},
]


@pytest.fixture
def payload():
    return bg.build_payload(DEVICES, list_name="rcn")


class TestItDoesNotShareAFailureWithWhatItRecovers:
    """Encrypting with `data/key.key` would make the record depend on the
    same secret as the thing it exists to recover from."""

    def test_the_passphrase_is_the_only_input(self, payload):
        blob = bg.seal(payload, PASS)
        assert bg.unseal(blob, PASS)["devices"]

    def test_a_wrong_passphrase_says_so_plainly(self, payload):
        blob = bg.seal(payload, PASS)
        with pytest.raises(bg.BreakglassError) as excinfo:
            bg.unseal(blob, "a-different-passphrase")
        assert "does not open" in str(excinfo.value)
        assert "Nothing else is wrong" in str(excinfo.value), (
            "at 3am, 'wrong passphrase' and 'corrupt file' lead to very "
            "different next actions")

    def test_it_never_reads_the_fernet_key(self):
        """Checked against the CODE, not the prose.

        The module's docstring explains at length why it must not depend on
        `data/key.key`, so a substring search over the whole file matches the
        explanation and fails on correct code -- the same shape as the
        spinner-literal assertion in the remote-panel tests.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(bg))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        assert not any("secrets_store" in name or "credentials" in name
                       for name in imported), imported

        # Docstring NODES, not `ast.get_docstring()` -- that returns cleaned,
        # dedented text which never equals the raw Constant it came from, so
        # comparing strings skips nothing.
        docstrings = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                continue
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))

        # DEFAULT_RECOVERY is prose written INTO the record for the person
        # opening it during an outage, and since key escrow (B5) it has to
        # tell them where the key goes back. A mention, named and exempted,
        # not a read. Anything else naming the file is still refused.
        prose = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign)
                    and any(getattr(t, "id", "") == "DEFAULT_RECOVERY"
                            for t in node.targets)):
                prose.update(id(n) for n in ast.walk(node.value))
        assert prose, "DEFAULT_RECOVERY was not found, so the exemption covers nothing"

        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings and id(node) not in prose):
                assert "key.key" not in node.value, node.value
        assert not any(isinstance(node, ast.Call)
                       and getattr(node.func, "id", "") == "open"
                       and any(isinstance(a, ast.Constant) and "key.key" in str(a.value)
                               for a in node.args)
                       for node in ast.walk(tree))

    def test_a_short_passphrase_is_refused(self, payload):
        with pytest.raises(bg.BreakglassError) as excinfo:
            bg.seal(payload, "short")
        assert "last way into the devices" in str(excinfo.value)

    def test_the_salt_is_per_record(self, payload):
        one = json.loads(bg.seal(payload, PASS))
        two = json.loads(bg.seal(payload, PASS))
        assert one["salt"] != two["salt"]
        assert one["ciphertext"] != two["ciphertext"]

    def test_the_envelope_carries_only_known_fields(self, payload):
        """Structure, not substrings.

        Two earlier versions of this test searched the envelope's text for
        `"r1"`. Both were wrong for the same reason, one field apart: the
        ciphertext is random base64, and so is the SALT, so a given
        two-character pair turns up by chance -- measured at roughly 1 run in
        200 for the salt alone. It passed locally and failed in the suite.

        The property is that the envelope holds a FIXED set of fields and
        none of the non-random ones is derived from the payload. Asserting
        the key set says that; grepping random bytes never could.
        """
        envelope = json.loads(bg.seal(payload, PASS))
        assert set(envelope) == {"breakglass", "kdf", "scrypt", "salt",
                                 "ciphertext"}

    def test_the_non_random_fields_derive_from_nothing(self, payload):
        """`kdf`, `scrypt` and the version are constants, so they are safe to
        compare literally -- and must stay that way."""
        envelope = json.loads(bg.seal(payload, PASS))
        readable = json.dumps({k: envelope[k]
                               for k in ("breakglass", "kdf", "scrypt")})
        for value in ("same", "en1", "admin", "r1", "rcn"):
            assert value not in readable

    #: Needles short enough to appear in random bytes by chance prove nothing.
    #: Measured 2026-09-23 over 2000 sealings of this fixture: the ciphertext
    #: is 953 bytes, and `b"r1"` -- two bytes -- appeared in **1.40%** of
    #: them, against 1.45% predicted by chance (953/65536). So this test
    #: failed roughly one run in seventy, at random, in a file about
    #: recovering from a lockout.
    #:
    #: **A security test that fails at random teaches you to ignore security
    #: test failures**, which is worse than not having it. Same reasoning as
    #: `redact.py`'s 8-character value floor, arrived at from the other
    #: direction: there a short value matches everywhere and corrupts; here a
    #: short value matches by accident and cries wolf.
    #:
    #: Four bytes puts the chance at 1 in 5 million per run, which is the
    #: difference between a check and a coin. The values that matter -- the
    #: password and the enable secret -- are what the test is actually about.
    MIN_NEEDLE_BYTES = 4

    def test_the_ciphertext_is_not_the_plaintext(self, payload):
        """Checked on the DECODED bytes, where a substring match means
        something -- not on their base64, where it does not."""
        import base64 as b64

        envelope = json.loads(bg.seal(payload, PASS))
        raw = b64.urlsafe_b64decode(envelope["ciphertext"] + "==")
        for value in (b"same", b"admin", b"cisco_iosxe"):
            assert len(value) >= self.MIN_NEEDLE_BYTES, value
            assert value not in raw

    def test_the_short_values_are_excluded_deliberately(self, payload):
        """Pinned so the hostname is not helpfully added back.

        `b"r1"` and `b"en1"` are in the fixture and are NOT asserted above.
        That is a decision about measurement, not an oversight, and without
        this test it reads like one.
        """
        assert all(len(v) < self.MIN_NEEDLE_BYTES for v in (b"r1", b"en1"))

    def test_the_stored_parameters_exclude_the_local_memory_ceiling(self, payload):
        """`maxmem` is a limit on this machine, not part of the derivation.

        It is also exactly why the first version raised: 128*n*r is precisely
        OpenSSL's 32 MiB default, so the call failed until it was lifted.
        """
        envelope = json.loads(bg.seal(payload, PASS))
        assert "maxmem" not in envelope["scrypt"]
        assert envelope["scrypt"]["n"] == 2 ** 15


class TestItIsVerifiableWithoutBeingRead:
    """A break-glass record nobody has opened is a hope, not a record -- and
    a verification that requires revealing everything means the only way to
    test it is to expose it."""

    def test_describe_prints_no_credential(self, payload):
        report = json.dumps(bg.describe(payload))
        assert "same" not in report
        assert "en1" not in report

    def test_it_still_proves_each_device_has_one(self, payload):
        rows = {row["hostname"]: row for row in bg.describe(payload)["devices"]}
        assert rows["r1"]["has_password"] and rows["r1"]["has_enable_secret"]
        assert rows["r2"]["has_password"] and not rows["r2"]["has_enable_secret"]

    def test_the_digest_is_salted_per_host(self, payload):
        """r1 and r2 share a password here. Showing one token for both would
        publish a fact about the fleet in a report that prints no values."""
        rows = {row["hostname"]: row for row in bg.describe(payload)["devices"]}
        assert rows["r1"]["digest"] != rows["r2"]["digest"]

    def test_the_digest_still_changes_with_the_password(self):
        one = bg.describe(bg.build_payload(
            [{"hostname": "r1", "password": "x"}], list_name="l"))
        two = bg.describe(bg.build_payload(
            [{"hostname": "r1", "password": "y"}], list_name="l"))
        assert one["devices"][0]["digest"] != two["devices"][0]["digest"]

    def test_incomplete_is_reported_not_hidden(self):
        report = bg.describe(bg.build_payload(
            [{"hostname": "r1", "password": ""}], list_name="l"))
        assert report["complete"] is False

    def test_an_empty_record_is_not_complete(self):
        assert bg.describe(bg.build_payload([], list_name="l"))["complete"] is False


class TestItRefusesToLiveInTheRepository:
    """`config_repo` is pushed to a private GitHub remote, and Phase 2b's
    history scan cannot un-publish what it finds."""

    def test_a_path_inside_a_git_repo_is_refused(self, tmp_path, payload):
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        with pytest.raises(bg.BreakglassError) as excinfo:
            bg.write_record(str(repo / "rec.bg"), payload, PASS)
        assert "git repository" in str(excinfo.value)

    def test_a_nested_path_is_refused_too(self, tmp_path, payload):
        """The check walks up; `deep/inside/a/repo` is still in the repo."""
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        deep = repo / "a" / "b" / "c"
        deep.mkdir(parents=True)
        with pytest.raises(bg.BreakglassError):
            bg.write_record(str(deep / "rec.bg"), payload, PASS)

    def test_the_refusal_says_where_to_put_it(self, tmp_path, payload):
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        with pytest.raises(bg.BreakglassError) as excinfo:
            bg.write_record(str(repo / "rec.bg"), payload, PASS)
        assert "removable media" in str(excinfo.value)

    def test_a_path_outside_is_written_owner_only(self, tmp_path, payload):
        out = bg.write_record(str(tmp_path / "rec.bg"), payload, PASS)
        assert out["ok"] is True
        assert out["mode"] == "0o600"

    def test_it_round_trips_from_disk(self, tmp_path, payload):
        path = str(tmp_path / "rec.bg")
        bg.write_record(path, payload, PASS)
        assert bg.read_record(path, PASS)["devices"][0]["hostname"] == "r1"


class TestTheRecordCarriesTheProcedure:
    """Someone opening this during an outage should not also have to find
    the runbook."""

    def test_it_names_the_console_path(self, payload):
        assert "telnet localhost 5000" in payload["recovery"]

    def test_it_says_not_to_redeploy(self, payload):
        assert "Do NOT redeploy" in payload["recovery"]

    def test_the_fields_are_listed_not_inferred(self):
        """Copying whatever a device dict holds means the next inventory
        field lands in a plaintext export without anyone deciding."""
        entry = bg.build_payload(
            [{"hostname": "r1", "password": "p", "surprise": "new-field"}],
            list_name="l")["devices"][0]
        assert "surprise" not in entry
        assert set(entry) == set(bg.FIELDS)


class TestTheCliNeverTakesAPassphraseOnTheCommandLine:
    """Anything on a command line is in the shell history and in `ps`."""

    SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "scripts", "nmas-breakglass")

    def _source(self):
        with open(self.SCRIPT, encoding="utf-8") as handle:
            return handle.read()

    def test_it_uses_getpass(self):
        assert "getpass.getpass" in self._source()

    def test_no_passphrase_argument_exists(self):
        source = self._source()
        assert "--passphrase" not in source
        assert "--password" not in source

    def test_export_confirms_the_passphrase(self):
        """A typo in a write-only field is only discovered when it is needed."""
        assert "_passphrase(confirm=True)" in self._source()

    def test_only_reveal_prints_a_credential(self):
        """export and verify must not, and reveal takes one device."""
        source = self._source()
        reveal = source[source.index("def _reveal"):source.index("def _current_list")]
        assert "entry['password']" in reveal

        # The exact expressions that would put a VALUE on screen. A substring
        # search for "password']" also matches `row['has_password']`, which is
        # a boolean and exactly what verify is supposed to print -- so the
        # crude matcher fails on correct code.
        leaks = ("entry['password']", 'entry["password"]',
                 "entry['secret']", 'entry["secret"]',
                 "['password']", "['secret']")
        export = source[source.index("def _export"):source.index("def _verify")]
        verify = source[source.index("def _verify"):source.index("def _reveal")]
        for name, body in (("export", export), ("verify", verify)):
            for leak in leaks:
                assert leak not in body, f"{name} reads a credential: {leak}"

    def test_reveal_warns_before_it_prints(self):
        source = self._source()
        reveal = source[source.index("def _reveal"):]
        warning = reveal[:reveal.index("read_record")]
        assert "scrollback" in warning

    def test_the_help_runs(self):
        out = subprocess.run([sys.executable, self.SCRIPT, "--help"],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0
        assert "export" in out.stdout and "verify" in out.stdout


# ---------------------------------------------------------------------------
# Key escrow (B5, 2026-09-25)
# ---------------------------------------------------------------------------

from cryptography.fernet import Fernet  # noqa: E402

PREFIX = "enc:v1:"


def _enc(key: bytes, value: str) -> str:
    return Fernet(key).encrypt(value.encode()).decode()


def _data_dir(tmp_path, key: bytes, *, stray_key: bytes = None) -> str:
    """A data directory shaped like the host's, every value under *key*.

    Nested JSON (credential profiles hold values two levels down) and a CSV
    in a list directory, because a collector that only looked at top-level
    settings would pass a fixture that had only those."""
    data = tmp_path / "data"
    (data / "lists" / "default").mkdir(parents=True)
    (data / "user_settings.json").write_text(json.dumps({
        "netbox_token": PREFIX + _enc(key, "tok-netbox"),
        "kea_password": PREFIX + _enc(key, "kea-pass"),
        "netbox_url": "http://not-a-secret",
    }))
    (data / "credential_profiles.json").write_text(json.dumps({
        "profiles": {"default": {"username": "admin",
                                 "password": PREFIX + _enc(stray_key or key, "dev-pass")}},
    }))
    rows = ["hostname,device_type,ip,username,password,secret,role",
            f"r1,cisco_xe,a,admin,{_enc(key, 'p1')},,router",
            f"s1,cisco_ios,b,admin,{_enc(key, 'p2')},{_enc(key, 'e2')},switch"]
    (data / "lists" / "default" / "devices.csv").write_text("\n".join(rows) + "\n")
    # A backup under a DIFFERENT key must not count: the application never
    # decrypts it, so it cannot make the live key look wrong.
    (data / "lists" / "default" / "devices.csv.bak-1").write_text(
        rows[0] + "\n" + f"r1,x,a,admin,{_enc(Fernet.generate_key(), 'old')},,r\n")
    (data / "key.key").write_bytes(key)
    return str(data)


class TestTheRecordEscrowsTheKey:
    """B5: nothing images the NMAS VM, so the key existed on one disk."""

    def test_the_payload_carries_it_and_describe_prints_only_a_fingerprint(self):
        key = Fernet.generate_key()
        payload = bg.build_payload(DEVICES, list_name="rcn", fernet_key=key + b"\n")
        assert payload["fernet_key"] == key.decode()
        report = bg.describe(payload)
        assert report["has_fernet_key"] is True
        assert report["key_fingerprint"] == bg.key_fingerprint(key)
        assert key.decode() not in json.dumps(report)

    def test_the_sealed_record_does_not_show_the_key(self):
        import base64 as b64

        key = Fernet.generate_key()
        envelope = json.loads(bg.seal(
            bg.build_payload(DEVICES, list_name="rcn", fernet_key=key), PASS))
        raw = b64.urlsafe_b64decode(envelope["ciphertext"] + "==")
        assert key not in raw and key not in json.dumps(envelope).encode()

    def test_a_record_from_before_escrow_says_so(self, payload):
        legacy = dict(payload)
        legacy.pop("fernet_key", None)
        assert bg.describe(legacy)["has_fernet_key"] is False
        with pytest.raises(bg.BreakglassError) as excinfo:
            bg.escrowed_key(legacy)
        assert "predates key escrow" in str(excinfo.value)


class TestTheKeyIsProvenByOpeningWhatIsStored:
    """A copy of the wrong key looks exactly like a working one."""

    def test_the_collector_finds_every_store_and_ignores_backups(self, tmp_path):
        key = Fernet.generate_key()
        stores = bg.live_ciphertexts(_data_dir(tmp_path, key), PREFIX)
        assert {k: len(v) for k, v in stores.items()} == {
            "user_settings.json": 2, "credential_profiles.json": 1,
            os.path.join("lists", "default", "devices.csv"): 3}

    def test_the_right_key_opens_everything(self, tmp_path):
        key = Fernet.generate_key()
        check = bg.check_key_opens(key, bg.live_ciphertexts(_data_dir(tmp_path, key), PREFIX))
        assert check["verdict"] == "opens"
        assert (check["opened"], check["total"]) == (6, 6)

    def test_a_different_key_opens_nothing_and_says_wrong_key(self, tmp_path):
        """The negative control: the whole reason for the check."""
        check = bg.check_key_opens(
            Fernet.generate_key(),
            bg.live_ciphertexts(_data_dir(tmp_path, Fernet.generate_key()), PREFIX))
        assert check["verdict"] == "wrong_key" and check["opened"] == 0

    def test_values_under_two_keys_are_mixed_not_a_pass(self, tmp_path):
        key = Fernet.generate_key()
        stores = bg.live_ciphertexts(
            _data_dir(tmp_path, key, stray_key=Fernet.generate_key()), PREFIX)
        check = bg.check_key_opens(key, stores)
        assert check["verdict"] == "mixed"
        assert check["stores"]["credential_profiles.json"] == {"opened": 0, "total": 1}

    def test_nothing_to_test_against_is_unproven_never_a_pass(self, tmp_path):
        (tmp_path / "empty").mkdir()
        check = bg.check_key_opens(Fernet.generate_key(),
                                   bg.live_ciphertexts(str(tmp_path / "empty"), PREFIX))
        assert check["verdict"] == "unproven" and check["total"] == 0

    def test_an_unreadable_store_is_named_and_withholds_the_pass(self, tmp_path):
        key = Fernet.generate_key()
        data = _data_dir(tmp_path, key)
        with open(os.path.join(data, "jenkins_checks.json"), "w") as handle:
            handle.write("{ not json")
        check = bg.check_key_opens(key, bg.live_ciphertexts(data, PREFIX))
        assert check["unreadable"] == ["jenkins_checks.json"]
        assert check["verdict"] == "unproven"

    def test_not_a_key_at_all_is_wrong_key(self, tmp_path):
        key = Fernet.generate_key()
        check = bg.check_key_opens(b"garbage", bg.live_ciphertexts(_data_dir(tmp_path, key), PREFIX))
        assert check["verdict"] == "wrong_key"


class TestRestoreNeverReplacesAKey:

    def test_it_writes_owner_only_with_the_same_fingerprint(self, tmp_path):
        key = Fernet.generate_key()
        out = bg.restore_key(bg.build_payload(DEVICES, list_name="l", fernet_key=key),
                             str(tmp_path / "key.key"))
        assert out["mode"] == "0o600"
        assert out["fingerprint"] == bg.key_fingerprint(key)
        assert (tmp_path / "key.key").read_bytes() == key

    def test_an_existing_file_is_refused_and_left_alone(self, tmp_path):
        target = tmp_path / "key.key"
        target.write_bytes(b"the-key-a-fresh-start-made")
        with pytest.raises(bg.BreakglassError) as excinfo:
            bg.restore_key(bg.build_payload(DEVICES, list_name="l",
                                            fernet_key=Fernet.generate_key()), str(target))
        assert "Nothing was written" in str(excinfo.value)
        assert target.read_bytes() == b"the-key-a-fresh-start-made"


def _cli():
    from importlib.machinery import SourceFileLoader
    import types

    path = TestTheCliNeverTakesAPassphraseOnTheCommandLine.SCRIPT
    module = types.ModuleType("nmas_breakglass_cli")
    module.__file__ = path
    SourceFileLoader("nmas_breakglass_cli", path).exec_module(module)
    return module


class TestVerifyLiveUsesTheEscrowedKey:
    """Driven through the CLI's own `_verify`, from a record on disk.

    The data directory's key file holds the RIGHT key in every case. A
    verify that tested the key on disk rather than the one in the record
    would pass the wrong-key case, which is exactly the failure escrow must
    not have: the copy is wrong and the check says it is fine."""

    def _run(self, tmp_path, monkeypatch, *, record_key, disk_key):
        cli = _cli()
        data = _data_dir(tmp_path, disk_key)
        record = str(tmp_path / "rec.bg")
        bg.write_record(record, bg.build_payload(DEVICES, list_name="l",
                                                 fernet_key=record_key), PASS)
        monkeypatch.setattr(cli, "_passphrase", lambda confirm=False: PASS)
        import argparse
        return cli._verify(argparse.Namespace(path=record, live=True, data_dir=data))

    def test_the_right_key_passes(self, tmp_path, monkeypatch, capsys):
        key = Fernet.generate_key()
        assert self._run(tmp_path, monkeypatch, record_key=key, disk_key=key) == 0
        out = capsys.readouterr().out
        assert "OPENS -- 6 of 6" in out and "same as the escrowed key" in out
        assert key.decode() not in out

    def test_a_wrong_escrowed_key_fails_even_though_the_disk_key_is_right(
            self, tmp_path, monkeypatch, capsys):
        rc = self._run(tmp_path, monkeypatch, record_key=Fernet.generate_key(),
                       disk_key=Fernet.generate_key())
        out = capsys.readouterr().out
        assert rc == 1
        assert "WRONG KEY -- 0 of 6" in out
        assert "DIFFERENT from the escrowed key" in out

    def test_reading_the_live_key_never_creates_one(self, tmp_path):
        (tmp_path / "empty").mkdir()
        assert _cli()._live_key(str(tmp_path / "empty")) == b""
        assert os.listdir(tmp_path / "empty") == []
