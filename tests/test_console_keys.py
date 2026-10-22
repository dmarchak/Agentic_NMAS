"""The console server's SSH key (modules/nsot/console_keys.py; docs/LAB9_PLAN.md section 8, "The
security addition" and its recommendation): Mercury generates an ed25519 pair, keeps the
private half encrypted in its credential store under a reference, and shows only the public
key and the exact `authorized_keys` line, which forces the bridge wrapper.

Every key here is generated at test time, in memory and in the test's own store; no key, and
no key's armour line, is written into a test or fixture file."""

import base64
import json
import shutil
import struct
import subprocess

import pytest

from modules import credentials
from modules import secrets_store
from modules.nsot import console_keys as K

REF = "console-lab"
USER = "mercury"
WRAPPER = "/usr/local/lib/nmas/nmas-console-bridge"
ALLOWLIST = "/etc/nmas/console-allowlist"


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    path = tmp_path / "credential_profiles.json"
    monkeypatch.setattr("modules.credentials._FILE", str(path))
    return path


def make(ref=REF, **over):
    args = dict(username=USER, wrapper_path=WRAPPER, allowlist_path=ALLOWLIST)
    args.update(over)
    return K.generate(ref, **args)


def wire_fields(public_key: str) -> list:
    """The public key's wire form read field by field (RFC 4253 strings), independently of
    the code under test: the key type and the 32-byte ed25519 point."""
    blob = base64.b64decode(public_key.split()[1])
    out, i = [], 0
    while i < len(blob):
        (n,) = struct.unpack(">I", blob[i:i + 4])
        out.append(blob[i + 4:i + 4 + n])
        i += 4 + n
    return out


class TestWhatIsReturned:
    def test_only_the_public_key_its_fingerprint_and_the_line(self):
        got = make()
        assert set(got) == {"ok", "ref", "username", "public_key", "fingerprint",
                            "authorized_keys_line"}
        assert (got["ok"], got["ref"], got["username"]) == (True, REF, USER)

    def test_the_public_key_is_one_ed25519_key_with_its_comment(self):
        public = make()["public_key"]
        kind, b64, comment = public.split(" ")
        assert (kind, comment) == ("ssh-ed25519", "mercury-console")
        fields = wire_fields(public)
        assert fields[0] == b"ssh-ed25519" and len(fields[1]) == 32 and len(fields) == 2
        assert base64.b64encode(base64.b64decode(b64)).decode() == b64

    def test_the_authorized_keys_line_is_exact(self):
        got = make()
        assert got["authorized_keys_line"] == (
            'restrict,command="/usr/local/lib/nmas/nmas-console-bridge '
            '/etc/nmas/console-allowlist" ' + got["public_key"])

    def test_the_fingerprint_is_what_ssh_keygen_prints(self, tmp_path):
        if not shutil.which("ssh-keygen"):
            pytest.skip("ssh-keygen is not installed here")
        got = make()
        pub = tmp_path / "key.pub"
        pub.write_text(got["public_key"] + "\n")
        out = subprocess.run(["ssh-keygen", "-l", "-E", "sha256", "-f", str(pub)],
                             capture_output=True, text=True, check=True).stdout.split()
        assert out[1] == got["fingerprint"] and out[-1] == "(ED25519)"

    def test_two_keys_are_two_keys(self):
        a = make("a")["public_key"]
        b = make("b")["public_key"]
        assert a != b


class TestThePrivateHalfIsKeptByReferenceOnly:
    def test_it_is_encrypted_in_the_store_and_loads_back_as_the_same_key(self, store):
        got = make()
        entry = json.loads(store.read_text())["ssh_keys"][REF]
        assert set(entry) == {"username", "private_key", "public_key", "created"}
        assert entry["username"] == USER and entry["public_key"] == got["public_key"]
        assert secrets_store.is_encrypted(entry["private_key"])
        private = credentials.get_ssh_key(REF)["private_key"]
        in_file = bool(private) and private in store.read_text()   # a bool: never printed
        assert private and not in_file
        username, pkey = K.load(REF)
        assert username == USER
        assert (pkey.get_name(), pkey.get_base64()) == ("ssh-ed25519",
                                                         got["public_key"].split()[1])

    def test_nothing_returned_or_logged_holds_any_of_it(self, caplog):
        with caplog.at_level("DEBUG"):
            got = make()
            K.load(REF)
        private = credentials.get_ssh_key(REF)["private_key"]
        pieces = [line for line in private.splitlines() if len(line) >= 16]
        assert pieces, "the private half has body lines to look for"
        said = caplog.text + repr(got) + repr(credentials.ssh_key_info(REF))
        leaked = [i for i, piece in enumerate(pieces) if piece in said]   # indexes only
        assert leaked == []
        assert REF in caplog.text                 # the reference is what is logged

    def test_the_info_never_holds_the_private_half(self):
        got = make()
        info = credentials.ssh_key_info(REF)
        assert set(info) == {"ref", "username", "public_key", "created"}
        assert info["public_key"] == got["public_key"]
        assert credentials.ssh_key_info("absent") is None

    def test_it_is_a_value_redaction_masks(self):
        make()
        private = credentials.get_ssh_key(REF)["private_key"].strip()
        label = credentials.device_credential_values().get(private)   # never printed
        assert label == "ssh-private-key"

    def test_the_store_logs_the_write_by_name(self, caplog):
        with caplog.at_level("INFO", logger="modules.credentials"):
            make()
        assert f"ssh_keys: +{REF}" in caplog.text
        assert f"stored SSH key '{REF}' for user {USER}" in caplog.text


class TestRefusals:
    def test_a_second_key_under_a_reference_is_refused_unless_replacing(self):
        first = make()
        with pytest.raises(credentials.SshKeyExists, match="already stored"):
            make()
        assert credentials.ssh_key_info(REF)["public_key"] == first["public_key"]
        second = make(replace=True)
        assert second["public_key"] != first["public_key"]
        assert credentials.ssh_key_info(REF)["public_key"] == second["public_key"]

    @pytest.mark.parametrize("field,value", [
        ("wrapper_path", "nmas-console-bridge"),            # relative
        ("wrapper_path", '/usr/bin/x" /etc/passwd'),        # a quote ends the command
        ("allowlist_path", "/etc/nmas/a list"),             # a space is a second word
        ("allowlist_path", "/etc/nmas/../shadow"),          # a '..' step
        ("allowlist_path", "/etc/nmas/.."),
        ("wrapper_path", "/x\n/y"),
        ("wrapper_path", ""),
        ("wrapper_path", None),
    ])
    def test_a_path_that_could_change_the_forced_command_is_refused(self, field, value):
        label = field.split("_")[0]                     # wrapper or allowlist
        with pytest.raises(ValueError, match=rf"^the {label} path .* is not an absolute path .*"
                                             r"with no '\.\.' step\)$"):
            make(**{field: value})
        assert credentials.ssh_key_info(REF) is None

    @pytest.mark.parametrize("ref", ["", "a b", "with'quote", "-dash", "x" * 129, None])
    def test_a_reference_that_is_not_a_name_is_refused(self, ref):
        with pytest.raises(ValueError, match="is not a name"):
            make(ref)

    @pytest.mark.parametrize("user", ["", "a b", "root;id", "-x", "x" * 33, None])
    def test_a_user_that_is_not_a_login_name_is_refused(self, user):
        with pytest.raises(ValueError, match="is not a login name"):
            make(username=user)
        assert credentials.ssh_key_info(REF) is None

    def test_both_halves_are_required_to_store(self):
        with pytest.raises(ValueError, match="both halves"):
            credentials.set_ssh_key(REF, username=USER, private_key="", public_key="x")
        with pytest.raises(ValueError, match="both halves"):
            credentials.set_ssh_key(REF, username=USER, private_key="x", public_key="")

    @pytest.mark.parametrize("public", [
        "ssh-rsa AAAA mercury-console", "ssh-ed25519 AAAA other", "ssh-ed25519 AAAA",
        "ssh-ed25519 AAAA mercury-console extra", None])
    def test_the_line_takes_only_one_ed25519_key_with_the_comment(self, public):
        with pytest.raises(ValueError, match="is not one ssh-ed25519 public key"):
            K.authorized_keys_line(public, WRAPPER, ALLOWLIST)

    def test_the_line_checks_its_paths(self):
        with pytest.raises(ValueError, match="^the allowlist path 'rel'"):
            K.authorized_keys_line("ssh-ed25519 AAAA mercury-console", WRAPPER, "rel")
        with pytest.raises(ValueError, match="^the wrapper path 'rel'"):
            K.authorized_keys_line("ssh-ed25519 AAAA mercury-console", "rel", ALLOWLIST)


class TestTheStoreItself:
    """`credentials.set_ssh_key`, `get_ssh_key` and `ssh_key_info` called directly (the
    mutation run of 2026-10-22: their defaults, keys and return value survived)."""

    def test_a_second_key_is_refused_by_default_naming_the_one_held(self):
        assert credentials.set_ssh_key(REF, username=USER, private_key="p1",
                                       public_key="ssh-ed25519 AAAA1 mercury-console") == \
            {"ok": True, "ref": REF}
        with pytest.raises(credentials.SshKeyExists) as exc:
            credentials.set_ssh_key(REF, username=USER, private_key="p2",
                                    public_key="ssh-ed25519 AAAA2 mercury-console")
        assert str(exc.value) == (f"SSH key '{REF}' is already stored (public key "
                                  "'ssh-ed25519 AAAA1 mercury-console'); replacing it is a "
                                  "separate decision")
        assert credentials.get_ssh_key(REF)["private_key"] == "p1"

    def test_what_is_read_back_is_exactly_what_was_stored(self, monkeypatch):
        monkeypatch.setattr(credentials.time, "time", lambda: 1234.5)
        credentials.set_ssh_key(REF, username=USER, private_key="p1",
                                public_key="ssh-ed25519 AAAA1 mercury-console")
        assert credentials.get_ssh_key(REF) == {
            "username": USER, "private_key": "p1",
            "public_key": "ssh-ed25519 AAAA1 mercury-console"}
        assert credentials.ssh_key_info(REF) == {
            "ref": REF, "username": USER, "public_key": "ssh-ed25519 AAAA1 mercury-console",
            "created": 1234.5}

    def test_an_entry_missing_its_fields_reads_as_empty_never_as_a_stand_in(self, store):
        store.write_text(json.dumps({"ssh_keys": {REF: {"note": "damaged by hand"}}}))
        assert credentials.get_ssh_key(REF) == {"username": "", "private_key": "",
                                                "public_key": ""}
        assert credentials.ssh_key_info(REF) == {"ref": REF, "username": "", "public_key": "",
                                                 "created": None}
        with pytest.raises(K.ConsoleKeyUnavailable, match="could not be decrypted"):
            K.load(REF)
        with pytest.raises(credentials.SshKeyExists, match=r"\(public key '\?'\)"):
            credentials.set_ssh_key(REF, username=USER, private_key="p",
                                    public_key="ssh-ed25519 AAAA mercury-console")


class TestLoadSaysWhyItCannot:
    def test_nothing_under_the_reference(self):
        with pytest.raises(K.ConsoleKeyUnavailable, match="no SSH key is stored under 'nope'"):
            K.load("nope")

    def test_a_private_half_that_will_not_decrypt(self, store):
        make()
        doc = json.loads(store.read_text())
        doc["ssh_keys"][REF]["private_key"] = "enc:v1:not-a-fernet-token"
        store.write_text(json.dumps(doc))
        with pytest.raises(K.ConsoleKeyUnavailable, match="could not be decrypted"):
            K.load(REF)

    def test_a_value_that_is_not_a_key_is_refused_without_its_words(self, store):
        credentials.set_ssh_key(REF, username=USER, private_key="Not-A-Key-Value-77",
                                public_key="ssh-ed25519 AAAA mercury-console")
        with pytest.raises(K.ConsoleKeyUnavailable) as exc:
            K.load(REF)
        assert "is not an ssh-ed25519 private key" in str(exc.value)
        assert "Not-A-Key-Value-77" not in str(exc.value)
        assert exc.value.__cause__ is None and exc.value.__suppress_context__
