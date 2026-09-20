"""host_vars staging and secret handling.

The critical property: an IOS password hash carries a per-hash salt and cannot
be regenerated from plaintext. The store therefore holds the **hash string**,
and templates emit it verbatim. If the store held plaintext, every round trip
would fail on those lines permanently.
"""

import os

import pytest

from modules.nsot import hostvars
from modules.nsot.parsers import get_parser

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "configs")


def _config(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


class TestHashDetection:
    @pytest.mark.parametrize("value", [
        "9 $9$abcdefghij", "5 $1$aB3x$K9mNpQ", "8 $8$xyz", "7 0822455D0A16",
        "$9$bare", "$1$bare",
    ])
    def test_hashes_are_detected(self, value):
        assert hostvars._looks_hashed(value)

    @pytest.mark.parametrize("value", ["0 admin", "public", "plaintextpw", ""])
    def test_plaintext_is_not_a_hash(self, value):
        assert not hostvars._looks_hashed(value)


class TestSecretExtraction:
    def test_user_secret_becomes_a_ref(self):
        out = get_parser("cisco_ios").parse(_config("s1_vios_l2.cfg"))
        user = next(u for u in out["users"] if u["name"] == "admin")
        assert user["secret_ref"] == "user_admin_secret"
        assert "$1$" not in str(user), "the hash leaked into the user entry"

    def test_hash_value_is_stored_verbatim(self):
        out = get_parser("cisco_ios").parse(_config("s1_vios_l2.cfg"))
        stored = out["secrets"]["user_admin_secret"]
        assert stored.startswith("5 $1$"), stored
        assert hostvars._looks_hashed(stored)

    def test_type_zero_plaintext_is_kept_as_is(self):
        """IOS-XE fixture uses `password 0 admin` — not a hash, still verbatim."""
        out = get_parser("cisco_xe").parse(_config("r1_c8000v.cfg"))
        assert out["secrets"]["user_admin_password"] == "0 admin"

    def test_snmp_community_becomes_a_ref(self):
        out = get_parser("cisco_ios").parse(_config("s1_vios_l2.cfg"))
        assert "snmp_community_ro" in out["secrets"]
        community = out["snmp"]["communities"][0]
        assert community["ref"] == "snmp_community_ro"
        assert "public" not in str(community)


class TestYamlOutput:
    def test_secrets_never_appear_in_yaml(self):
        out = get_parser("cisco_ios").parse(_config("s1_vios_l2.cfg"))
        text = hostvars.to_yaml(out)
        for value in out["secrets"].values():
            assert value not in text, "a secret value was written to YAML"

    def test_secret_refs_are_listed(self):
        out = get_parser("cisco_ios").parse(_config("s1_vios_l2.cfg"))
        data = hostvars.from_yaml(hostvars.to_yaml(out))
        assert "user_admin_secret" in data["secret_refs"]

    def test_yaml_is_deterministic(self):
        out = get_parser("cisco_ios").parse(_config("s1_vios_l2.cfg"))
        assert hostvars.to_yaml(out) == hostvars.to_yaml(out)

    def test_lineno_is_excluded(self):
        out = get_parser("cisco_xe").parse(_config("r1_c8000v.cfg"))
        assert "lineno" not in hostvars.to_yaml(out)


class TestStaging:
    def test_writes_to_staging_not_the_repo(self, tmp_path):
        """Phase 3a is read-only with respect to git."""
        out = get_parser("cisco_ios").parse(_config("s1_vios_l2.cfg"))
        path = hostvars.write_staged(str(tmp_path), out)
        assert ".nsot" in path and "staging" in path
        assert os.path.exists(path)
        assert not os.path.exists(os.path.join(tmp_path, "host_vars"))

    def test_round_trips_through_disk(self, tmp_path):
        out = get_parser("cisco_ios").parse(_config("s1_vios_l2.cfg"))
        hostvars.write_staged(str(tmp_path), out)
        loaded = hostvars.read_staged(str(tmp_path), "s1")
        assert loaded["hostname"] == "s1"
        assert len(loaded["interfaces"]) == len(out["interfaces"])

    def test_list_staged(self, tmp_path):
        for name, platform in (("s1_vios_l2.cfg", "cisco_ios"),
                               ("r1_c8000v.cfg", "cisco_xe")):
            hostvars.write_staged(str(tmp_path), get_parser(platform).parse(_config(name)))
        assert hostvars.list_staged(str(tmp_path)) == ["r1", "s1"]

    def test_store_secrets_dry_run_writes_nothing(self):
        out = get_parser("cisco_ios").parse(_config("s1_vios_l2.cfg"))
        result = hostvars.store_secrets(out, "s1", dry_run=True)
        assert result["dry_run"] is True
        assert result["count"] == len(out["secrets"])
        # Names and kinds only — never values.
        for entry in result["moved"]:
            assert set(entry) == {"ref", "kind"}

    def test_hash_kind_is_recorded(self):
        out = get_parser("cisco_ios").parse(_config("s1_vios_l2.cfg"))
        moved = {e["ref"]: e["kind"]
                 for e in hostvars.store_secrets(out, "s1")["moved"]}
        assert moved["s1:user_admin_secret"] == "hash"
        assert moved["s1:snmp_community_ro"] == "plaintext"


class TestCommittedIntentNeverHoldsASecretValue:
    """The masking contract, at the one place that writes to git.

    Committed host_vars hold ``secret_refs`` — names. The credential store
    holds values. A preview masks; a deploy resolves in memory and calls
    ``assert_no_mask()``. Nothing in between ever writes a value to disk, and
    this is the guard that makes that structural rather than aspirational.
    """

    @pytest.fixture
    def store(self, tmp_path, monkeypatch):
        """A credential store holding one real secret for s1."""
        from modules import credentials
        values = {"s1:user_admin_secret": "$9$RealHashValue$notregenerable"}
        monkeypatch.setattr(credentials, "get_template_secret",
                            lambda name: values.get(name, ""))
        monkeypatch.setattr(credentials, "list_template_secrets",
                            lambda: [{"name": n, "secret_kind": "hash",
                                      "rotatable": False} for n in values])
        return values

    def test_to_yaml_emits_refs_not_values(self, store):
        from modules.nsot import hostvars
        text = hostvars.to_yaml({"hostname": "s1",
                                 "secrets": {"user_admin_secret": store["s1:user_admin_secret"]}})
        assert "secret_refs" in text
        assert store["s1:user_admin_secret"] not in text

    def test_write_committed_refuses_a_resolved_value(self, tmp_path, store):
        from modules.nsot import hostvars
        with pytest.raises(hostvars.SecretLeak):
            hostvars.write_committed_text(
                str(tmp_path), "s1",
                f"hostname: s1\nbanner: {store['s1:user_admin_secret']}\n")

    def test_write_committed_refuses_a_secrets_mapping(self, tmp_path, store):
        from modules.nsot import hostvars
        with pytest.raises(hostvars.SecretLeak):
            hostvars.write_committed_text(
                str(tmp_path), "s1", "hostname: s1\nsecrets:\n  a: b\n")

    def test_a_clean_document_is_written(self, tmp_path, store):
        from modules.nsot import hostvars
        path = hostvars.write_committed_text(
            str(tmp_path), "s1", "hostname: s1\nsecret_refs:\n- user_admin_secret\n")
        with open(path, encoding="utf-8") as fh:
            assert store["s1:user_admin_secret"] not in fh.read()

    def test_no_committed_file_in_the_repo_holds_a_value(self, tmp_path, store):
        """The property stated directly, over every file in the store."""
        from modules.nsot import hostvars
        repo = str(tmp_path)
        hostvars.write_committed(repo, {
            "hostname": "s1",
            "secrets": {"user_admin_secret": store["s1:user_admin_secret"]},
            "interfaces": [],
        })
        for name in hostvars.list_committed(repo):
            with open(hostvars.committed_path(repo, name), encoding="utf-8") as fh:
                body = fh.read()
            for value in store.values():
                assert value not in body, f"{name}.yml carries a resolved secret"

    def test_hydration_happens_in_memory_and_is_not_written(self, tmp_path, store):
        from modules.nsot import hostvars
        repo = str(tmp_path)
        hostvars.write_committed(repo, {
            "hostname": "s1",
            "secrets": {"user_admin_secret": store["s1:user_admin_secret"]},
        })
        committed = hostvars.read_committed(repo, "s1")
        assert "secrets" not in committed

        live = hostvars.hydrate_secrets(committed, "s1")
        assert live["secrets"]["user_admin_secret"] == store["s1:user_admin_secret"]

        with open(hostvars.committed_path(repo, "s1"), encoding="utf-8") as fh:
            assert store["s1:user_admin_secret"] not in fh.read()

    def test_a_reference_with_no_stored_value_is_not_silently_empty(self, tmp_path, store):
        from modules.nsot import hostvars
        live = hostvars.hydrate_secrets(
            {"hostname": "s1", "secret_refs": ["missing_ref"]}, "s1")
        assert "missing_ref" not in live["secrets"]
