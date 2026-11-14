"""The read-only account added to a device through intent (C2657; the operator, 2026-11-13: "C2657
as proposed, hand check included"), on a credential store in this test's own folder; no device.

A ``users`` entry naming ``read-account:profile:<name>`` takes the account's NAME and PASSWORD
from the credential store's ``read_accounts`` (`credentials.read_account_login`, through
`hostvars.stored_value`, the one resolver), never from intent:

- **it renders** the measured form, ``username <account> algorithm-type scrypt secret
  <value>``, on both shipped platforms, the value resolved in memory at render; its name comes
  from the store when intent leaves it out. Privilege 1 is not printed: IOS-XE never prints its
  default privilege (measured on r2, 2026-11-13: `username mercury-ro privilege 1 algorithm-type
  scrypt secret …` sent, read back as `username mercury-ro secret 9 …`, so verify failed
  "account mercury-ro is there with privilege unset (1), not 1"), so the render matches what
  the device holds and verify reads it back;
- **it resolves from its own store only**: a template or profile secret spelled like the
  reference is never read for it;
- **it is masked on the way out**: the preview's masked render, its payload, the receipt's
  program and a refusal never carry the value; the preview names the masked value by its
  reference; intent carrying the password is refused at commit;
- **a missing account refuses by name**: no read account on the profile, or an entry naming
  another account than the store's, resolves nothing, the preview says it has no value, and the
  deploy's mask guard refuses it naming the reference and where to set it;
- **an account is added, never changed**: a device already holding that username with another
  line is refused by the change-of-account guard (`deploy.assert_credentials_unchanged`), and
  once the device's own form is captured after the verified deploy the line renders as the
  device keeps it, so a later deploy sends nothing for it;
- **the hash binds**: the program a plan hashes and the one its apply recomputes resolve the
  same value from the store, so they hash alike, and a password replaced between the two moves
  the hash (the apply refuses, `routes.deploy`'s recomputed fingerprint);
- **Set value… never sets it per device**: the card draws it not settable, naming where it is
  set.

IPv6 is not involved: nothing here parses, stores or connects to an address (the fixtures'
management addresses ride through the render unchanged).
"""

import os

import pytest

from modules import credentials as C
from modules.nsot import hostvars

REF = "read-account:profile:default"
RO_NAME, RO_PW, RO_PW2 = "mercury-ro", "ReadOnly-Not-Real-7731", "ReadOnly-Not-Real-8842"
DEPLOY_PW = "Deploy-Not-Real-5531"
DEVICE_FORM = "9 $9$DeviceMadeItNotReal$abcdefghijklmnop"
FIXTURES = {"cisco_iosxe": "r1_c8000v.cfg", "cisco_ios": "s1_vios_l2.cfg"}
LIST, HOST = "net", "edge1"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_FILE", str(tmp_path / "credential_profiles.json"))
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    C.save_profile("default", username="netops", password=DEPLOY_PW)
    return tmp_path


def _set_account(password=RO_PW):
    C.set_read_account("default", RO_NAME, password, actor="op@example.com", verified="access")


def _committed(platform, entry=None):
    """A real capture's intent as committed (references only), the read account then added
    under ``users`` as the operator's entry adds it, with the capture's own values stored for
    device edge1 of network net."""
    from modules.nsot.parsers import get_parser
    from tests.js_source import read_shipped

    capture = read_shipped(os.path.join(os.path.dirname(__file__), "fixtures", "configs",
                                        FIXTURES[platform]))
    parsed = get_parser(platform).parse(capture)
    for ref, value in (parsed.get("secrets") or {}).items():
        C.set_template_secret(C.template_secret_key(LIST, HOST, ref), value, list_name=LIST)
    doc = hostvars.from_yaml(hostvars.to_yaml(parsed))
    doc["users"] = list(doc.get("users") or []) + [
        entry if entry is not None else {"privilege": 1, "secret_ref": REF}]
    return capture, doc


def _artifact(capture, doc, platform="cisco_iosxe"):
    from modules.nsot.render_artifact import build_artifact

    return build_artifact(HOST, capture, platform, host_vars=hostvars.hydrate_secrets(
        doc, HOST, LIST), template=f"{platform}/base.j2", template_approved=True)


def _line(text, start="username " + RO_NAME):
    got = [l for l in text.splitlines() if l.startswith(start)]
    assert len(got) == 1, (start, got)
    return got[0]


class TestItRenders:
    @pytest.mark.parametrize("platform", ["cisco_iosxe", "cisco_ios"])
    def test_the_account_renders_its_measured_form_with_the_store_s_name_and_value(
            self, store, platform):
        from modules.nsot.deploy import prepare_device

        _set_account()
        capture, doc = _committed(platform)
        prepared = prepare_device(_artifact(capture, doc, platform))
        assert _line(prepared["config"]) == (
            f"username {RO_NAME} algorithm-type scrypt secret {RO_PW}")

    def test_a_name_written_in_intent_that_is_the_store_s_renders_the_same(self, store):
        from modules.nsot.deploy import prepare_device

        _set_account()
        capture, doc = _committed("cisco_iosxe", {"name": RO_NAME, "privilege": 1,
                                                  "secret_ref": REF})
        assert _line(prepare_device(_artifact(capture, doc))["config"]).endswith(RO_PW)

    def test_the_reference_is_named_where_every_reference_is(self, store):
        _set_account()
        _capture, doc = _committed("cisco_iosxe")
        assert REF in hostvars.named_refs(doc)
        assert hostvars.read_account_profile(REF) == "default"
        assert hostvars.read_account_profile("user_admin_secret") == ""


class TestVerifyReadsItBack:
    """The deploy's verify reads the account back as the device prints it (the operator,
    2026-11-13: r2's deploy of the account failed verify, "account mercury-ro is there with
    privilege unset (1), not 1", because the program sent `privilege 1`, which IOS-XE never
    prints)."""

    @pytest.mark.parametrize("platform", ["cisco_iosxe", "cisco_ios"])
    def test_the_program_s_account_line_reads_back_from_the_device_s_own_line(
            self, store, platform):
        from modules.nsot.deploy import merge_commands, prepare_device
        from modules.nsot.verify_scope import account_held

        _set_account()
        capture, doc = _committed(platform)
        program = merge_commands(prepare_device(_artifact(capture, doc, platform))["config"],
                                 capture)
        (sent,) = [c for c in program if c.startswith(f"username {RO_NAME}")]
        # What r2 printed after the deploy (its running config, 2026-11-13, masked here): no
        # privilege, and the secret in the type the device made from what was sent.
        running = capture.replace("\nend", f"\nusername {RO_NAME} secret {DEVICE_FORM}\nend", 1)
        assert account_held(sent, running) == "", account_held(sent, running)

    @pytest.mark.parametrize("platform", ["cisco_iosxe", "cisco_ios"])
    def test_any_other_privilege_is_still_rendered(self, store, platform):
        """Only the default is left out: a privilege-15 account keeps its `privilege 15`, so
        the device and verify still see it."""
        from modules.nsot.deploy import prepare_device

        _set_account()
        capture, doc = _committed(platform, entry={"name": RO_NAME, "privilege": 15,
                                                   "secret_ref": REF})
        assert _line(prepare_device(_artifact(capture, doc, platform))["config"]) == (
            f"username {RO_NAME} privilege 15 algorithm-type scrypt secret {RO_PW}")


class TestItResolvesFromItsOwnStoreOnly:
    def test_a_template_or_profile_secret_spelled_like_the_reference_is_never_read(self, store):
        decoy_own, decoy_profile = "Decoy-Template-Not-Real-1", "Decoy-Profile-Not-Real-2"
        C.set_template_secret(C.profile_secret_key(LIST, REF), decoy_profile, list_name=LIST)
        assert hostvars.stored_value(LIST, HOST, REF) == "", \
            "no read account set: nothing resolves, not the profile secret of the same name"
        _set_account()
        assert hostvars.stored_value(LIST, HOST, REF) == RO_PW
        # A device's own value is its device form, written only by the capture (Set value… is
        # refused for this reference, below); the store's value is used until there is one.
        C.set_template_secret(C.template_secret_key(LIST, HOST, REF), decoy_own,
                              secret_kind="hash", list_name=LIST)
        assert hostvars.stored_value(LIST, HOST, REF) == decoy_own


    def test_a_reference_resolves_its_own_profile_s_account_never_another_s(self, store):
        """Two profiles, two read-only accounts: each reference resolves its own profile's,
        by its exact name (the hand check of 2026-11-13, mutant P3: the first profile's
        account taken for any reference survived, every test holding one profile)."""
        C.save_profile("site:lab", username="netops-lab", password="Deploy-Lab-Not-Real-9")
        C.set_read_account("site:lab", "lab-ro", "ReadOnly-Lab-Not-Real-6", actor="op@example.com",
                           verified="access")
        _set_account()
        assert hostvars.stored_value(LIST, HOST, "read-account:profile:site:lab") == \
            "ReadOnly-Lab-Not-Real-6"
        assert hostvars.stored_value(LIST, HOST, REF) == RO_PW
        assert C.read_account_login("site:lab")["username"] == "lab-ro"
        assert C.read_account_login("default")["username"] == RO_NAME
        assert C.read_account_login("role:none")["ok"] is False, "no chain: a profile's own"


class TestItIsMaskedOnTheWayOut:
    def test_the_preview_masks_it_and_names_it_by_its_reference(self, store):
        from modules.nsot import secret_refs
        from modules.nsot.deploy import prepare_device
        from modules.nsot.render_artifact import MASK
        from modules.outbound import mask_payload

        _set_account()
        capture, doc = _committed("cisco_iosxe")
        art = _artifact(capture, doc)
        assert _line(art.rendered_masked) == (
            f"username {RO_NAME} algorithm-type scrypt secret {MASK}")
        assert REF in art.masked_refs
        assert RO_PW not in repr(art.summary())
        # The payload a preview returns carries the program as sent, masked on the way out,
        # then each masked value named by its reference (`device_v2._deploy_card`'s order).
        program = prepare_device(art)["config"].splitlines()
        out = secret_refs.label_by_ref(mask_payload({"to_add": program}), doc)
        assert RO_PW not in repr(out)
        assert (f"username {RO_NAME} algorithm-type scrypt secret "
                f"<redacted:{REF}>") in out["to_add"]

    def test_the_receipt_masks_it(self, store, monkeypatch):
        from modules.nsot import receipts
        from modules.nsot.deploy import prepare_device

        _set_account()
        capture, doc = _committed("cisco_iosxe")
        program = prepare_device(_artifact(capture, doc))["config"].splitlines()
        monkeypatch.setattr(receipts, "intent_commits", lambda *_a, **_k: {})
        (row,) = receipts.rows_for({"results": [{"device": HOST, "commands": program,
                                                 "outcome": "deployed"}]},
                                   list_name=LIST, action="deploy", actor="op@example.com",
                                   actor_kind="person")
        assert RO_PW not in repr(row)
        assert any(l.startswith(f"username {RO_NAME} ") and "<redacted:" in l
                   for l in row["program"]), row["program"][:5]

    def test_intent_carrying_the_password_is_refused_at_commit(self, store):
        _set_account()
        text = hostvars.to_yaml({"hostname": HOST, "banner": f"motd {RO_PW}"})
        with pytest.raises(hostvars.SecretLeak) as exc:
            hostvars.assert_no_secret_values(text, HOST)
        assert REF in str(exc.value) and RO_PW not in str(exc.value)


class TestAMissingAccountRefusesByName:
    def _refusal(self, doc, capture):
        from modules.nsot.deploy import prepare_device
        from modules.nsot.intent_edit import no_value_words
        from modules.nsot.render_artifact import MaskedContentError

        art = _artifact(capture, doc)
        (line,) = [l for l in art.rendered_masked.splitlines()
                   if l.startswith("username ") and REF in l]
        assert line.endswith(f"secret <missing-secret:{REF}>") and "•" not in line, line
        assert f"(no value: {REF}; a deploy is refused" in no_value_words(line)
        with pytest.raises(MaskedContentError) as exc:
            prepare_device(art)
        return str(exc.value)

    def test_no_read_account_on_the_profile(self, store):
        capture, doc = _committed("cisco_iosxe")
        doc["users"] = [u for u in doc["users"] if u.get("secret_ref") != REF] + [
            {"name": RO_NAME, "privilege": 1, "secret_ref": REF}]
        words = self._refusal(doc, capture)
        assert f"no read-only account for {REF}" in words, words
        assert "Settings › Credentials" in words and "Nothing was sent" in words

    def test_no_read_account_and_no_name(self, store):
        capture, doc = _committed("cisco_iosxe")
        assert f"no read-only account for {REF}" in self._refusal(doc, capture)

    def test_an_entry_naming_another_account(self, store):
        _set_account()
        capture, doc = _committed("cisco_iosxe", {"name": "someone-else", "privilege": 1,
                                                  "secret_ref": REF})
        words = self._refusal(doc, capture)
        assert f"no read-only account for {REF}" in words and RO_PW not in words


class TestAnAccountIsAddedNeverChanged:
    def test_a_device_already_holding_the_username_otherwise_is_refused(self, store):
        from modules.nsot.deploy import prepare_device
        from modules.nsot.render_artifact import CredentialWouldChange

        _set_account()
        capture, doc = _committed("cisco_iosxe")
        # The device's own line as r2 printed it (2026-11-13): no privilege, IOS-XE's default.
        held = capture.replace("\nend", f"\nusername {RO_NAME} secret "
                               f"{DEVICE_FORM}\nend", 1)
        assert held != capture
        with pytest.raises(CredentialWouldChange) as exc:
            prepare_device(_artifact(held, doc))
        assert f"username:{RO_NAME}" in str(exc.value)
        assert RO_PW not in str(exc.value) and DEVICE_FORM.split()[1] not in str(exc.value)

    def test_after_the_capture_the_line_is_the_device_s_and_nothing_is_sent_for_it(
            self, store):
        from modules.nsot import credential_rotation as CR
        from modules.nsot.deploy import merge_commands, prepare_device

        _set_account()
        capture, doc = _committed("cisco_iosxe")
        after = capture.replace("\nend", f"\nusername {RO_NAME} secret "
                                f"{DEVICE_FORM}\nend", 1)
        (got,) = [c for c in CR.capture_typed_secrets(LIST, HOST, doc, after)
                  if c["ref"] == REF]
        assert got == {"account": RO_NAME, "ref": REF, "captured": True, "why": ""}
        key = C.template_secret_key(LIST, HOST, REF)
        assert C.template_secret_kind(key) == "hash"
        assert C.get_template_secret(key) == DEVICE_FORM
        config = prepare_device(_artifact(after, doc))["config"]
        assert _line(config) == f"username {RO_NAME} secret {DEVICE_FORM}"
        assert not [c for c in merge_commands(config, after) if c.startswith("username ")]
        # The Intent check's render, which resolves no value, draws the same form.
        captured = hostvars.captured_read_accounts(LIST, HOST, doc)
        assert captured == {REF}
        user = next(u for u in hostvars.read_account_users(doc, captured=captured)["users"]
                    if u.get("secret_ref") == REF)
        assert user["secret_kind"] == "secret" and user["name"] == RO_NAME


class TestTheHashBinds:
    def test_plan_and_apply_hash_alike_and_a_replaced_password_moves_it(self, store):
        from modules.nsot.deploy import command_fingerprint, merge_commands, prepare_device

        _set_account()
        capture, doc = _committed("cisco_iosxe")

        def program():
            return merge_commands(prepare_device(_artifact(capture, doc))["config"], capture)

        planned = program()
        assert any(c.startswith(f"username {RO_NAME} ") for c in planned)
        assert command_fingerprint(program()) == command_fingerprint(planned)
        masked_before = _artifact(capture, doc).rendered_masked
        _set_account(RO_PW2)                    # Replace its password… between plan and apply
        assert _artifact(capture, doc).rendered_masked == masked_before, \
            "the masked text alone cannot tell; the hash over the program sent must"
        assert command_fingerprint(program()) != command_fingerprint(planned)


class TestSetValueNeverSetsItPerDevice:
    def test_the_card_draws_it_not_settable_and_the_check_refuses(self, store, monkeypatch):
        from modules.nsot import secret_refs

        # The capture's typed values ask the network's set records (none here), in this
        # test's own folder.
        monkeypatch.setattr(secret_refs, "_repo", lambda _l: str(store / "config_repo"))
        _set_account()
        _capture, doc = _committed("cisco_iosxe")
        got = secret_refs.listing(LIST, HOST, intent=doc)
        (row,) = [r for r in got["refs"] if r["ref"] == REF]
        assert row["settable"] is False and "Settings › Credentials" in row["why_not"]
        assert row["state"] == "held" and RO_NAME in row["for"]
        checks = secret_refs.check(LIST, HOST, REF, "Typed-Not-Real-1", "Typed-Not-Real-1",
                                   "a reason", intent=doc)
        (refusal,) = [c for c in checks if c["name"] == "not the read-only account"]
        assert refusal["ok"] is False and "Settings › Credentials" in refusal["detail"]
        ok = secret_refs.check(LIST, HOST, "user_admin_secret", "Typed-Not-Real-1",
                               "Typed-Not-Real-1", "a reason", intent=doc)
        assert all(c["ok"] for c in ok if c["name"] == "not the read-only account")


class TestACustomPrivilegeLevel:
    """The read-only account at privilege 3 with the reads that level may run (the operator,
    2026-11-13: "mercury-ro at privilege 3, with `privilege exec level 3 <command>` lines for
    exactly the reads that need it, through intent and the template, previewed and approved
    by hash like r2's account"). The device lines here are in the form r2 printed its account
    in (2026-11-13), with `privilege 3` where IOS prints a privilege that is not its default;
    that form is the first deploy's verify to measure."""

    LINES = [{"level": 3, "command": "show telemetry ietf subscription", "all": False},
             {"level": 3, "command": "ping", "all": True},
             {"level": 3, "command": "ping ipv6", "all": True}]
    #: What the render writes and the device stores for LINES (C3580): after the telemetry line,
    #: its leading words at the same level, longest first, as r4 stored them (its golden,
    #: 2026-11-14), and `show` among them at 3, since LINES restores nothing; `ping` is its own
    #: entry, so `ping ipv6` writes no line for it.
    SENT = ["privilege exec level 3 show telemetry ietf subscription",
            "privilege exec level 3 show telemetry ietf", "privilege exec level 3 show telemetry",
            "privilege exec level 3 show",
            "privilege exec all level 3 ping", "privilege exec all level 3 ping ipv6"]

    def _doc(self, platform):
        capture, doc = _committed(platform, entry={"privilege": 3, "secret_ref": REF})
        doc["privilege_exec"] = [dict(e) for e in self.LINES]
        return capture, doc

    @pytest.mark.parametrize("platform", ["cisco_iosxe", "cisco_ios"])
    def test_the_account_renders_privilege_3_after_the_lines_of_its_level(self, store, platform):
        from modules.nsot.deploy import prepare_device

        _set_account()
        capture, doc = self._doc(platform)
        config = prepare_device(_artifact(capture, doc, platform))["config"].splitlines()
        account = f"username {RO_NAME} privilege 3 algorithm-type scrypt secret {RO_PW}"
        assert _line("\n".join(config)) == account
        at = [config.index(line) for line in self.SENT]
        assert at == sorted(at) and at[-1] < config.index(account), (at, config.index(account))

    @pytest.mark.parametrize("platform", ["cisco_iosxe", "cisco_ios"])
    def test_a_device_whose_golden_lacks_the_account_is_sent_it_added_never_refused(
            self, store, platform):
        """r2, 2026-11-13: its running configuration holds the account at privilege 1 (the
        deploy whose verify failed saved nothing), its golden does not. The change-of-account
        guard compares the golden's line, so the privilege-3 deploy adds the account."""
        from modules.nsot.deploy import dangerous_in, merge_commands, prepare_device

        _set_account()
        capture, doc = self._doc(platform)
        assert f"username {RO_NAME}" not in capture
        program = merge_commands(prepare_device(_artifact(capture, doc, platform))["config"],
                                 capture)
        assert program == self.SENT + [
            f"username {RO_NAME} privilege 3 algorithm-type scrypt secret {RO_PW}"], program
        assert dangerous_in(program) == [], "no line here needs a reason"

    @pytest.mark.parametrize("platform", ["cisco_iosxe", "cisco_ios"])
    def test_verify_reads_privilege_3_back_and_says_when_the_device_holds_another(
            self, store, platform):
        from modules.nsot.deploy import merge_commands, prepare_device
        from modules.nsot.verify_scope import account_held, read_back

        _set_account()
        capture, doc = self._doc(platform)
        program = merge_commands(prepare_device(_artifact(capture, doc, platform))["config"],
                                 capture)
        sent = program[-1]
        printed = "\n".join(self.SENT + [f"username {RO_NAME} privilege 3 secret {DEVICE_FORM}"])
        running = capture.replace("\nend", f"\n{printed}\nend", 1)
        assert account_held(sent, running) == ""
        got = read_back(program, running)
        assert got["missing"] == [] and got["checked"] == len(program), got
        # The account as r2 holds it now, at the default privilege, never printed.
        at_1 = running.replace(f"username {RO_NAME} privilege 3 secret",
                               f"username {RO_NAME} secret")
        assert account_held(sent, at_1) == (
            f"account {RO_NAME} is there with privilege unset (1), not 3")
        assert RO_PW not in " ".join(read_back(program, at_1)["missing"])

    def test_a_device_whose_golden_holds_the_account_at_privilege_1_is_refused(self, store):
        """An account is added, never changed: once a golden holds the privilege-1 line, a
        deploy that would re-send it at privilege 3 is refused, naming the account and never
        a value."""
        from modules.nsot.deploy import prepare_device
        from modules.nsot.render_artifact import CredentialWouldChange

        _set_account()
        capture, doc = self._doc("cisco_iosxe")
        held = capture.replace("\nend", f"\nusername {RO_NAME} secret {DEVICE_FORM}\nend", 1)
        with pytest.raises(CredentialWouldChange) as exc:
            prepare_device(_artifact(held, doc))
        assert f"username:{RO_NAME}" in str(exc.value)
        assert RO_PW not in str(exc.value) and DEVICE_FORM.split()[1] not in str(exc.value)

    def test_after_the_capture_the_privilege_3_line_is_the_device_s_and_nothing_is_sent(
            self, store):
        from modules.nsot import credential_rotation as CR
        from modules.nsot.deploy import merge_commands, prepare_device

        _set_account()
        capture, doc = self._doc("cisco_iosxe")
        printed = "\n".join(self.SENT + [f"username {RO_NAME} privilege 3 secret {DEVICE_FORM}"])
        after = capture.replace("\nend", f"\n{printed}\nend", 1)
        (got,) = [c for c in CR.capture_typed_secrets(LIST, HOST, doc, after)
                  if c["ref"] == REF]
        assert got["captured"] is True, got
        config = prepare_device(_artifact(after, doc))["config"]
        assert _line(config) == f"username {RO_NAME} privilege 3 secret {DEVICE_FORM}"
        assert merge_commands(config, after) == []

    def test_the_preview_masks_the_account_and_shows_the_lines_whole(self, store):
        from modules.nsot.deploy import merge_commands, prepare_device
        from modules.redact import redact_text

        _set_account()
        capture, doc = self._doc("cisco_iosxe")
        program = merge_commands(prepare_device(_artifact(capture, doc))["config"], capture)
        shown = [redact_text(c) for c in program]
        assert shown[:len(self.SENT)] == self.SENT, "nothing of a privilege line is a secret"
        assert RO_PW not in " ".join(shown) and shown[len(self.SENT)].startswith(
            f"username {RO_NAME} privilege 3 algorithm-type scrypt secret ")


class TestAnActionWritesTheAccountsEntry:
    """`hostvars.with_read_account`: the one `users` entry, written for a device by code (the
    operator, 2026-11-13: an "Add the read-only account…" action, no hand-typed YAML)."""

    def test_a_device_without_it_gains_the_entry_and_no_name_or_password(self, store):
        before = {"hostname": HOST, "users": [{"name": "admin", "privilege": 15}]}
        doc, change = hostvars.with_read_account(before, "default", 3)
        assert change == "added"
        assert doc["users"] == [{"name": "admin", "privilege": 15},
                                {"privilege": 3, "secret_ref": REF}]
        assert before["users"] == [{"name": "admin", "privilege": 15}], "the caller's is its own"

    def test_an_entry_at_another_privilege_is_moved_and_said(self, store):
        held = {"users": [{"privilege": 1, "secret_ref": REF}]}
        doc, change = hostvars.with_read_account(held, "default", 3)
        assert change == "privilege 1 to 3" and doc["users"] == [
            {"privilege": 3, "secret_ref": REF}]
        assert held["users"][0]["privilege"] == 1
        again, change = hostvars.with_read_account(doc, "default", 3)
        assert change == "" and again == doc

    def test_another_profile_s_account_is_its_own_entry(self, store):
        held = {"users": [{"privilege": 1, "secret_ref": REF}]}
        doc, change = hostvars.with_read_account(held, "role:router", 3)
        assert change == "added" and doc["users"][0] == {"privilege": 1, "secret_ref": REF}
        assert doc["users"][1] == {"privilege": 3,
                                   "secret_ref": "read-account:profile:role:router"}

    def test_what_it_writes_renders_the_account(self, store):
        from modules.nsot.deploy import prepare_device

        _set_account()
        capture, doc = _committed("cisco_iosxe", entry={"privilege": 1, "secret_ref": REF})
        doc, _change = hostvars.with_read_account(doc, "default", 3)
        assert _line(prepare_device(_artifact(capture, doc))["config"]) == (
            f"username {RO_NAME} privilege 3 algorithm-type scrypt secret {RO_PW}")
