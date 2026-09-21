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

        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings):
                assert "key.key" not in node.value, node.value

    def test_a_short_passphrase_is_refused(self, payload):
        with pytest.raises(bg.BreakglassError) as excinfo:
            bg.seal(payload, "short")
        assert "last way into the devices" in str(excinfo.value)

    def test_the_salt_is_per_record(self, payload):
        one = json.loads(bg.seal(payload, PASS))
        two = json.loads(bg.seal(payload, PASS))
        assert one["salt"] != two["salt"]
        assert one["ciphertext"] != two["ciphertext"]

    def test_the_envelope_metadata_leaks_nothing(self, payload):
        """The parts an onlooker can read: everything except the ciphertext.

        The first version searched the WHOLE envelope, ciphertext included,
        for `"r1"`. Base64 of a random token contains a given two-character
        pair often, so it passed alone and failed in the full suite -- a test
        that fails on correct code, from the matcher rather than the property.
        """
        envelope = json.loads(bg.seal(payload, PASS))
        readable = json.dumps({k: v for k, v in envelope.items()
                               if k != "ciphertext"})
        for value in ("same", "en1", "admin", "r1", "rcn"):
            assert value not in readable

    def test_the_ciphertext_is_not_the_plaintext(self, payload):
        """Checked on the DECODED bytes, where a substring match means
        something -- not on their base64, where it does not."""
        import base64 as b64

        envelope = json.loads(bg.seal(payload, PASS))
        raw = b64.urlsafe_b64decode(envelope["ciphertext"] + "==")
        for value in (b"same", b"en1", b"admin", b"r1"):
            assert value not in raw

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
