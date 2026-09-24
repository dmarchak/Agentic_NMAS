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
                 for e in hostvars.store_secrets(out, "s1", list_name="lab")["moved"]}
        assert moved["lab:s1:user_admin_secret"] == "hash"
        assert moved["lab:s1:snmp_community_ro"] == "plaintext"


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
        values = {"lab:s1:user_admin_secret": "$9$RealHashValue$notregenerable"}
        monkeypatch.setattr(credentials, "get_template_secret",
                            lambda name: values.get(name, ""))
        monkeypatch.setattr(credentials, "list_template_secrets",
                            lambda: [{"name": n, "secret_kind": "hash",
                                      "rotatable": False} for n in values])
        return values

    def test_to_yaml_emits_refs_not_values(self, store):
        from modules.nsot import hostvars
        text = hostvars.to_yaml({"hostname": "s1",
                                 "secrets": {"user_admin_secret": store["lab:s1:user_admin_secret"]}})
        assert "secret_refs" in text
        assert store["lab:s1:user_admin_secret"] not in text

    def test_write_committed_refuses_a_resolved_value(self, tmp_path, store):
        from modules.nsot import hostvars
        with pytest.raises(hostvars.SecretLeak):
            hostvars.write_committed_text(
                str(tmp_path), "s1",
                f"hostname: s1\nbanner: {store['lab:s1:user_admin_secret']}\n")

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
            assert store["lab:s1:user_admin_secret"] not in fh.read()

    def test_no_committed_file_in_the_repo_holds_a_value(self, tmp_path, store):
        """The property stated directly, over every file in the store."""
        from modules.nsot import hostvars
        repo = str(tmp_path)
        hostvars.write_committed(repo, {
            "hostname": "s1",
            "secrets": {"user_admin_secret": store["lab:s1:user_admin_secret"]},
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
            "secrets": {"user_admin_secret": store["lab:s1:user_admin_secret"]},
        })
        committed = hostvars.read_committed(repo, "s1")
        assert "secrets" not in committed

        live = hostvars.hydrate_secrets(committed, "s1", "lab")
        assert live["secrets"]["user_admin_secret"] == store["lab:s1:user_admin_secret"]

        with open(hostvars.committed_path(repo, "s1"), encoding="utf-8") as fh:
            assert store["lab:s1:user_admin_secret"] not in fh.read()

    def test_a_reference_with_no_stored_value_is_not_silently_empty(self, tmp_path, store):
        from modules.nsot import hostvars
        live = hostvars.hydrate_secrets(
            {"hostname": "s1", "secret_refs": ["missing_ref"]}, "s1")
        assert "missing_ref" not in live["secrets"]


class TestTheSecretCheckDoesNotRefuseLegitimateCommits:
    """A false refusal blocks the entire intent path behind a scary error.

    The first version compared by plain substring with a 3-character floor. A
    stored value of ``admin`` would have refused ``username admin privilege
    15`` — ordinary configuration, in the field it belongs in, reported as a
    leaked secret.
    """

    @pytest.fixture
    def short_secret(self, monkeypatch):
        from modules import credentials
        values = {"s1:user_admin_name": "admin"}
        monkeypatch.setattr(credentials, "get_template_secret",
                            lambda name: values.get(name, ""))
        monkeypatch.setattr(credentials, "list_template_secrets",
                            lambda: [{"name": n, "secret_kind": "plaintext",
                                      "rotatable": True} for n in values])
        return values

    @pytest.fixture
    def long_secret(self, monkeypatch):
        from modules import credentials
        values = {"s1:snmp_community_ro": "Str0ngC0mmunityValue"}
        monkeypatch.setattr(credentials, "get_template_secret",
                            lambda name: values.get(name, ""))
        monkeypatch.setattr(credentials, "list_template_secrets",
                            lambda: [{"name": n, "secret_kind": "plaintext",
                                      "rotatable": True} for n in values])
        return values

    def test_a_short_value_does_not_refuse_ordinary_config(self, tmp_path, short_secret):
        from modules.nsot import hostvars
        hostvars.write_committed_text(
            str(tmp_path), "s1",
            "hostname: s1\nusers:\n- username admin privilege 15\n")

    def test_the_floor_is_documented_not_incidental(self):
        from modules.nsot import hostvars
        assert hostvars.MIN_CHECKABLE_SECRET >= 8

    def test_a_partial_token_match_is_not_a_leak(self, tmp_path, long_secret):
        """Str0ngC0mmunityValue inside Str0ngC0mmunityValueExtended is a
        different value, not this one."""
        from modules.nsot import hostvars
        hostvars.write_committed_text(
            str(tmp_path), "s1",
            "hostname: s1\nbanner: Str0ngC0mmunityValueExtended\n")

    def test_a_whole_token_match_is_still_refused(self, tmp_path, long_secret):
        from modules.nsot import hostvars
        with pytest.raises(hostvars.SecretLeak):
            hostvars.write_committed_text(
                str(tmp_path), "s1",
                f"hostname: s1\nbanner: {long_secret['s1:snmp_community_ro']}\n")

    def test_the_refusal_names_the_field_and_the_secret(self, tmp_path, long_secret):
        from modules.nsot import hostvars
        with pytest.raises(hostvars.SecretLeak) as exc:
            hostvars.write_committed_text(
                str(tmp_path), "s1",
                f"hostname: s1\nbanner: {long_secret['s1:snmp_community_ro']}\n")
        message = str(exc.value)
        assert "s1:snmp_community_ro" in message
        assert "banner" in message
        assert "line 2" in message

    def test_the_refusal_says_what_to_write_instead(self, tmp_path, long_secret):
        from modules.nsot import hostvars
        with pytest.raises(hostvars.SecretLeak) as exc:
            hostvars.write_committed_text(
                str(tmp_path), "s1",
                f"hostname: s1\nbanner: {long_secret['s1:snmp_community_ro']}\n")
        assert "secret_ref" in str(exc.value)
        assert "snmp_community_ro" in str(exc.value)

    def test_another_devices_secret_is_not_checked(self, tmp_path, long_secret):
        """Refs are namespaced by device; s2's store entry is not s1's business."""
        from modules.nsot import hostvars
        hostvars.write_committed_text(
            str(tmp_path), "s2",
            f"hostname: s2\nbanner: {long_secret['s1:snmp_community_ro']}\n")


class TestToYamlIsAFixedPointOverItsOwnOutput:
    """``to_yaml`` destroyed every ``secret_ref`` on a second pass.

    It strips ``secrets`` on the way out and recomputes ``secret_refs`` *from
    that key*. Feed its own output back in — which is exactly what
    read-staged → write-committed does — and the key is gone, so the refs come
    back empty.

    The existing fixed-point test could not see this. It runs parse → render →
    parse and compares ``to_yaml`` of both; both inputs come from the parser
    and therefore always carry ``secrets``. The *parser* was tested for a fixed
    point; the *serialiser* never was.
    """

    def _doc(self):
        return {"hostname": "s4",
                "secrets": {"snmp_community_ro": "abc", "user_admin_secret": "xyz"},
                "interfaces": []}

    def test_a_second_pass_preserves_the_refs(self):
        from modules.nsot import hostvars
        once = hostvars.to_yaml(self._doc())
        twice = hostvars.to_yaml(hostvars.from_yaml(once))
        assert once == twice

    def test_a_third_pass_is_still_stable(self):
        from modules.nsot import hostvars
        text = hostvars.to_yaml(self._doc())
        for _ in range(3):
            text_next = hostvars.to_yaml(hostvars.from_yaml(text))
            assert text_next == text
            text = text_next

    def test_the_refs_survive_by_name(self):
        from modules.nsot import hostvars
        twice = hostvars.from_yaml(
            hostvars.to_yaml(hostvars.from_yaml(hostvars.to_yaml(self._doc()))))
        assert twice["secret_refs"] == ["snmp_community_ro", "user_admin_secret"]

    def test_an_empty_secrets_mapping_still_means_no_refs(self):
        """Present-but-empty is a real answer and must not fall back."""
        from modules.nsot import hostvars
        doc = hostvars.from_yaml(hostvars.to_yaml(
            {"hostname": "s4", "secrets": {}, "secret_refs": ["stale"]}))
        assert doc["secret_refs"] == []

    def test_round_tripping_through_the_committed_store_keeps_refs(self, tmp_path):
        from modules.nsot import hostvars
        repo = str(tmp_path)
        hostvars.write_committed(repo, self._doc())
        first = hostvars.read_committed(repo, "s4")
        hostvars.write_committed(repo, first)
        second = hostvars.read_committed(repo, "s4")
        assert second["secret_refs"] == ["snmp_community_ro", "user_admin_secret"]


class TestCommittedIntentMustBePrintableAscii:
    """The first of the two boundaries.

    Catching it at commit means the character never reaches a plan, so nobody
    confirms a command list that cannot be sent. The deploy path checks again
    before connecting: this is a value an operator types, and a guard on typed
    input belongs where the typing happens *and* where the sending happens.
    """

    def test_an_em_dash_is_refused_at_commit(self, tmp_path):
        from modules.nsot import hostvars
        with pytest.raises(hostvars.NonPrintableContent):
            hostvars.write_committed_text(
                str(tmp_path), "s4",
                "hostname: s4\ndescription: NSoT-managed — CSCI 5840 Lab 4\n")

    def test_the_error_names_character_codepoint_and_column(self, tmp_path):
        from modules.nsot import hostvars
        with pytest.raises(hostvars.NonPrintableContent) as exc:
            hostvars.write_committed_text(
                str(tmp_path), "s4", "hostname: s4\ndescription: a — b\n")
        message = str(exc.value)
        assert "U+2014" in message and "column" in message

    def test_the_ascii_version_is_accepted(self, tmp_path):
        from modules.nsot import hostvars
        hostvars.write_committed_text(
            str(tmp_path), "s4",
            "hostname: s4\ndescription: NSoT-managed - CSCI 5840 Lab 4\n")

    def test_write_committed_refuses_it_too(self, tmp_path):
        """Both entry points, not just the editor."""
        from modules.nsot import hostvars
        with pytest.raises(hostvars.NonPrintableContent):
            hostvars.write_committed(str(tmp_path),
                                     {"hostname": "s4", "banner": "a — b"})


class TestSecretsAreScopedToTheirDeviceList:
    """The collision that made one network deploy another network's credentials.

    The key was ``<hostname>:<ref>`` in one installation-wide store, built by
    four separate f-strings in three modules. Two lists that each contain a
    device called ``r1`` — the actual name in the reference lab, and the
    likeliest name in any second one — shared one key. The second list's
    extraction silently replaced the first's, and the first network then
    rendered and deployed the second network's SNMP community, with **every
    guard on the deploy path satisfied**: none of them asks which network a
    secret belongs to.
    """

    @pytest.fixture
    def store(self, tmp_path, monkeypatch):
        from modules import credentials
        monkeypatch.setattr(credentials, "_FILE",
                            str(tmp_path / "credential_profiles.json"))
        return credentials

    def test_two_lists_with_the_same_device_name_do_not_collide(self, store):
        from modules.nsot import hostvars

        hostvars.store_secrets({"secrets": {"snmp_community_ro": "NET-A-VALUE"}},
                               "r1", dry_run=False, list_name="campus")
        hostvars.store_secrets({"secrets": {"snmp_community_ro": "NET-B-VALUE"}},
                               "r1", dry_run=False, list_name="branch")

        assert store.get_template_secret(
            store.template_secret_key("campus", "r1", "snmp_community_ro")) == "NET-A-VALUE"
        assert store.get_template_secret(
            store.template_secret_key("branch", "r1", "snmp_community_ro")) == "NET-B-VALUE"
        assert len(store.list_template_secrets()) == 2

    def test_hydration_resolves_this_lists_secret(self, store):
        """The end the bug came out of: the wrong value reaching a render."""
        from modules.nsot import hostvars

        for list_name, value in (("campus", "NET-A-VALUE"), ("branch", "NET-B-VALUE")):
            hostvars.store_secrets({"secrets": {"snmp_community_ro": value}},
                                   "r1", dry_run=False, list_name=list_name)

        intent = {"hostname": "r1", "secret_refs": ["snmp_community_ro"]}
        campus = hostvars.hydrate_secrets(intent, "r1", "campus")
        branch = hostvars.hydrate_secrets(intent, "r1", "branch")

        assert campus["secrets"]["snmp_community_ro"] == "NET-A-VALUE"
        assert branch["secrets"]["snmp_community_ro"] == "NET-B-VALUE"

    def test_listing_can_be_filtered_to_one_list(self, store):
        from modules.nsot import hostvars
        for list_name in ("campus", "branch"):
            hostvars.store_secrets({"secrets": {"snmp_community_ro": "v"}},
                                   "r1", dry_run=False, list_name=list_name)

        assert [e["name"] for e in store.list_template_secrets("campus")] == \
               ["campus:r1:snmp_community_ro"]
        assert len(store.list_template_secrets()) == 2

    def test_a_write_may_not_replace_another_lists_secret(self, store):
        """Defence for the case that caused the bug: a hand-built key.

        List-scoped keys already make the collision impossible through
        `template_secret_key`. This guard covers a caller that constructs the
        key itself, which is exactly what the four f-strings were.
        """
        store.set_template_secret("campus:r1:snmp_community_ro", "NET-A",
                                  list_name="campus")
        with pytest.raises(store.SecretOwnedByAnotherList) as excinfo:
            store.set_template_secret("campus:r1:snmp_community_ro", "NET-B",
                                      list_name="branch")

        assert "campus" in str(excinfo.value)
        assert store.get_template_secret("campus:r1:snmp_community_ro") == "NET-A"

    def test_a_list_may_update_its_own_secret(self, store):
        """Rotation must still work — the guard is about OTHER lists."""
        store.set_template_secret("campus:r1:snmp_community_ro", "OLD",
                                  list_name="campus")
        store.set_template_secret("campus:r1:snmp_community_ro", "NEW",
                                  list_name="campus")
        assert store.get_template_secret("campus:r1:snmp_community_ro") == "NEW"

    def test_the_key_is_built_in_exactly_one_place(self):
        """Four f-strings in three modules is how the shapes drifted apart.

        **Comments are skipped, and that is not a weakening.** This grepped
        every line and matched a comment in `onboard.py` explaining why the
        line beneath it is deliberately *not* shaped like a secret key — the
        documented hazard that *a pattern which can appear in English needs
        an anchor*, and that the better the comment, the more likely it
        quotes the code it explains. A prose mention of the shape is not a
        construction of the key, and a check that cannot tell them apart
        pressures the next author into deleting the explanation.
        """
        import inspect
        import re
        import subprocess

        from modules import credentials

        out = subprocess.run(
            ["grep", "-rn", "-E", r"\{(hostname|host)\}:\{", "--include=*.py",
             "modules/", "routes/", "scripts/"],
            capture_output=True, text=True).stdout
        # The one legitimate construction is the body of template_secret_key.
        owner = inspect.getsource(credentials.template_secret_key)
        strays = []
        for line in out.splitlines():
            if not line.strip():
                continue
            code = line.split(":", 2)[-1].strip()
            if code.startswith("#") or code.startswith('"""'):
                continue          # a mention, not a construction
            if code in [l.strip() for l in owner.splitlines()]:
                continue          # the one legitimate construction
            strays.append(line)
        assert strays == [], (
            "a template-secret key is built outside template_secret_key():\n"
            + "\n".join(strays))


class TestLegacySecretMigration:
    """Existing keys predate list scoping and all belong to the only list."""

    @pytest.fixture
    def store(self, tmp_path, monkeypatch):
        from modules import credentials
        monkeypatch.setattr(credentials, "_FILE",
                            str(tmp_path / "credential_profiles.json"))
        credentials.set_template_secret("r1:snmp_community_ro", "LEGACY-A")
        credentials.set_template_secret("s1:user_admin_secret", "LEGACY-B",
                                        secret_kind="hash")
        return credentials

    def test_dry_run_writes_nothing(self, store):
        result = store.migrate_template_secrets_to_list_scope("Default")
        assert result["dry_run"] is True
        assert result["count"] == 2
        assert store.get_template_secret("r1:snmp_community_ro") == "LEGACY-A"
        assert store.get_template_secret("default:r1:snmp_community_ro") == ""

    def test_apply_moves_keys_and_preserves_values_and_kinds(self, store):
        store.migrate_template_secrets_to_list_scope("Default", dry_run=False)

        assert store.get_template_secret("default:r1:snmp_community_ro") == "LEGACY-A"
        assert store.get_template_secret("default:s1:user_admin_secret") == "LEGACY-B"
        assert store.get_template_secret("r1:snmp_community_ro") == ""

        kinds = {e["name"]: e["secret_kind"] for e in store.list_template_secrets()}
        assert kinds["default:s1:user_admin_secret"] == "hash"
        assert kinds["default:r1:snmp_community_ro"] == "plaintext"

    def test_migration_is_idempotent(self, store):
        store.migrate_template_secrets_to_list_scope("Default", dry_run=False)
        again = store.migrate_template_secrets_to_list_scope("Default", dry_run=False)

        assert again["count"] == 0
        assert len(again["skipped"]) == 2
        assert store.get_template_secret("default:r1:snmp_community_ro") == "LEGACY-A"

    def test_a_migrated_key_is_owned_and_guarded(self, store):
        """After migration the ownership guard protects it."""
        store.migrate_template_secrets_to_list_scope("Default", dry_run=False)
        with pytest.raises(store.SecretOwnedByAnotherList):
            store.set_template_secret("default:r1:snmp_community_ro", "X",
                                      list_name="branch")
