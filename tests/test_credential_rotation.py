"""Credential rotation: generation, the confirm fingerprint, and the states.

The states matter most. "Did it work" has five answers here, and two of them
are easy to conflate in a way that destroys a completed change: a device that
rotated but whose new password has not reached the startup file is **rotated**,
and reverting it to fix that would undo real work to solve a bookkeeping
problem.
"""

import math
import os

import pytest

from cryptography.fernet import InvalidToken

from modules.nsot import credential_rotation as cr


class TestGeneration:
    def test_length_and_entropy(self):
        assert cr.LENGTH == 32
        assert len(cr.CHARSET) == 78
        assert 32 * math.log2(len(cr.CHARSET)) > 200

    def test_the_charset_excludes_what_the_cli_would_eat(self):
        for ch in "? \"'\\`|":
            assert ch not in cr.CHARSET, ch

    def test_the_charset_excludes_the_router_db_delimiter(self):
        """':' would produce an unparseable Oxidized row.

        The helper refuses it rather than corrupting the file, so the failure
        is safe — but it lands AFTER the device is rotated and committed,
        stranding the credential live with the boot copy behind. At 32 chars
        from 79, that was 1 - (78/79)**32 = 33.5% of rotations.
        """
        assert ":" not in cr.CHARSET

    def test_no_charset_character_can_break_a_router_db_row(self):
        """Every character, checked against the file format it lands in."""
        for ch in cr.CHARSET:
            assert ch not in ":\n\r", ch
            assert ch.isprintable(), ch

    def test_the_charset_excludes_what_OUR_REDACTOR_cannot_mask(self):
        """`redact._VALUE` refuses a token starting with these.

        A password beginning with `[` would not be positionally masked in a
        log — a defensive measure added elsewhere constraining the generator
        here, which is invisible until it is in a log file.
        """
        from modules import redact

        for ch in "[]<>()":
            assert ch not in cr.CHARSET, ch
            # And prove the coupling rather than restating it.
            line = f"snmp-server community {ch}notmasked RO"
            assert redact.redact_positional(line) == line

    def test_a_generated_password_is_always_maskable(self):
        from modules import redact

        for _ in range(25):
            pw = cr.generate_password("r2")
            out = redact.redact_positional(
                f"username admin privilege 15 algorithm-type scrypt secret {pw}")
            assert pw not in out
            assert "<redacted:user_password>" in out

    def test_no_surrounding_whitespace(self):
        for _ in range(25):
            pw = cr.generate_password("r2")
            assert pw == pw.strip()

    def test_passwords_are_unique(self):
        seen = {cr.generate_password("r2") for _ in range(50)}
        assert len(seen) == 50

    def test_it_uses_secrets_not_random(self):
        import inspect
        source = inspect.getsource(cr)
        assert "secrets.choice" in source
        assert "random.choice" not in source

    def test_a_guard_rejection_retries_but_a_programming_error_does_not(
            self, monkeypatch):
        """A broad except turns 'called it wrong' into a confident wrong answer.

        The first version caught Exception, swallowed a TypeError from calling
        assert_printable with the wrong arity, retried a hundred times, and
        reported that the charset disagreed with the guards.
        """
        def _boom(*a, **k):
            raise TypeError("wrong arity")
        monkeypatch.setattr("modules.nsot.hostvars.assert_printable", _boom)

        with pytest.raises(TypeError):
            cr.generate_password("r2")


class TestTheCommandAndItsMask:
    def test_the_command_matches_what_was_verified_on_the_device(self):
        cmd = cr.rotation_command("admin", 15, "SECRET")
        assert cmd == "username admin privilege 15 algorithm-type scrypt secret SECRET"

    def test_no_privilege_renders_without_the_clause(self):
        assert cr.rotation_command("bob", None, "S") == \
            "username bob algorithm-type scrypt secret S"

    def test_the_masked_form_carries_no_value(self):
        masked = cr.masked_command("admin", 15)
        assert "<generated>" in masked
        assert masked.startswith("username admin privilege 15 algorithm-type scrypt")


class TestTheConfirmFingerprint:
    BASE = dict(device_identity="uid:r2", username="admin", privilege=15,
                capture_hash="cap123")

    def test_it_is_stable(self):
        assert cr.operation_fingerprint(**self.BASE) == \
            cr.operation_fingerprint(**self.BASE)

    def test_it_does_not_depend_on_the_password(self):
        """The operator cannot confirm bytes they may not see."""
        import inspect
        source = inspect.getsource(cr.operation_fingerprint)
        # The BODY, not the docstring — which explains the exclusion and so
        # naturally contains the word.
        body = source.split('"""')[-1]
        assert "password" not in body

    @pytest.mark.parametrize("field,value", [
        ("device_identity", "uid:r3"),
        ("username", "operator"),
        ("privilege", 1),
        ("capture_hash", "changed"),
    ])
    def test_every_bound_property_moves_it(self, field, value):
        changed = dict(self.BASE, **{field: value})
        assert cr.operation_fingerprint(**changed) != \
            cr.operation_fingerprint(**self.BASE)

    def test_changing_the_charset_moves_it(self, monkeypatch):
        before = cr.operation_fingerprint(**self.BASE)
        monkeypatch.setattr(cr, "CHARSET", cr.CHARSET + "?")
        assert cr.operation_fingerprint(**self.BASE) != before


class TestPersistenceFailureIsNotRotationFailure:
    """Amendment 3, made structural rather than remembered."""

    def test_the_states_are_distinct(self):
        states = {cr.ROTATED_PERSISTED, cr.ROTATED_UNVERIFIED, cr.REVERTED,
                  cr.REVERT_FAILED, cr.NOT_STARTED}
        assert len(states) == 5

    def test_a_persistence_failure_is_recognised_as_rotated(self):
        result = {"state": cr.ROTATED_UNVERIFIED, "device": "r2"}
        assert cr.persistence_failed(result) is True

        summary = cr.summarise(result)
        assert "ROTATED and committed" in summary
        assert "not reverted" in summary.lower()
        assert "redeploy would boot the OLD password" in summary

    def test_a_verify_failure_reports_the_device_unchanged(self):
        summary = cr.summarise({"state": cr.REVERTED, "device": "r2"})
        assert "restored and proven" in summary
        assert "device is unchanged" in summary

    def test_a_failed_revert_says_locked_out_and_where_to_go(self):
        summary = cr.summarise({"state": cr.REVERT_FAILED, "device": "r2"})
        assert "MAY BE LOCKED OUT" in summary
        assert "serial console" in summary

    def test_success_claims_redeploy_survival_only_when_persisted(self):
        assert "survives redeploy" in cr.summarise(
            {"state": cr.ROTATED_PERSISTED, "device": "r2"})
        assert "survives redeploy" not in cr.summarise(
            {"state": cr.ROTATED_UNVERIFIED, "device": "r2"})

    def test_a_local_fault_may_never_be_reported_as_a_device_verdict(self):
        """The rule the r2 run broke, stated where it cannot drift."""
        import inspect
        assert "requires having asked the device" in inspect.getdoc(cr)
        summary = cr.summarise({"state": cr.REVERTED_UNPROVEN, "device": "r2"})
        assert "MAY BE LOCKED OUT" not in summary
        assert "local fault" in summary

    def test_only_the_verify_step_is_named_as_reverting(self):
        """Documented in one place so the rule cannot drift."""
        import inspect
        assert cr.VERIFY == "verify_new_credential"
        assert "Only :data:`VERIFY` failing reverts" in inspect.getdoc(cr)


ORIGINAL_LINE = "username admin privilege 15 password OldPlaintext"
ORIGINAL_PLAINTEXT = "OldPlaintext"
POST_CONFIG = "username admin privilege 15 secret 9 $9$saltsalt$hashhash"


class NetmikoAuthenticationException(Exception):
    """Named to match the real one — the classifier keys on the class NAME."""


class _Router:
    """The device itself: it accepts exactly one password at a time.

    The point of modelling this at all is that a fresh login must be judged by
    what the device would do, not by a stubbed verdict. A dict carrying an
    encrypted password, or a password the push never set, fails here the way
    it would fail on hardware.
    """

    #: Verbatim from r2, IOS-XE 17.06.01a.
    REFUSAL = ("ERROR: Can not have both a user password and a user secret.\n"
               "Please choose one or the other.\n")
    CONFIRM = ("This operation will remove all username related configurations "
               "with same name.Do you want to continue? [confirm]")

    def __init__(self, password=ORIGINAL_PLAINTEXT):
        self.password = password
        self.logins = []            # every kwargs dict ConnectHandler received
        self.running = ORIGINAL_LINE
        self.entry = "password"     # which kind of entry the account holds
        self.exists = True
        self.stores = "9"           # what the running config shows after a push
        self.honours_new_secret = True   # False: stores it, won't authenticate
        self.dead = False           # refuses every credential
        self.local_fault = None     # raised before any "connection" happens
        self.awaiting_confirm = False

    def login(self, **kwargs):
        if self.local_fault is not None:
            raise self.local_fault
        self.logins.append(dict(kwargs))
        if self.dead or not self.exists \
                or kwargs.get("password") != self.password:
            raise NetmikoAuthenticationException(
                f"Authentication to device {kwargs.get('ip')} failed")
        return _Conn(self)

    def apply(self, line):
        """Apply one config line; return what the device would print.

        This models the behaviour measured on r2 rather than the behaviour the
        command's name suggests. Setting a secret on a username that already
        holds a ``password`` entry is REFUSED — well-formed, so no
        ``% Invalid input``, just a plain-English decline and no change. Every
        device in the fleet is in that state, so the original one-command
        rotation could not have worked on any of them.
        """
        line = line.strip()
        if self.awaiting_confirm:
            self.awaiting_confirm = False
            self.exists = False
            self.running = ""
            return ""

        parts = line.split()
        if parts[:2] == ["no", "username"]:
            if not self.exists:
                return ""
            self.awaiting_confirm = True
            return self.CONFIRM

        if parts[:1] != ["username"]:
            return ""

        for keyword in ("secret", "password", "nopassword"):
            if keyword in parts:
                break
        else:
            return ""

        if keyword == "nopassword":
            self.entry = "nopassword"
            self.exists = True
            self.running = line
            return ""

        value = parts[parts.index(keyword) + 1]
        if keyword == "password":
            # Symmetric: the device refuses a password over a secret entry for
            # the same reason it refuses a secret over a password one. This is
            # what the REVERT walks into after a successful push.
            if self.exists and self.entry == "secret":
                return self.REFUSAL
            self.exists, self.entry = True, "password"
            self.running, self.password = line, value
            return ""

        # keyword == "secret"
        if self.exists and self.entry == "password":
            return self.REFUSAL           # refused; nothing changes

        self.exists, self.entry = True, "secret"
        if "algorithm-type" in parts:
            # IOS hashes it: the running config never shows the plaintext
            # again, which is why the verify must carry the value from memory.
            self.running = (f"username {parts[1]} privilege 15 "
                            f"secret {self.stores} $9$saltsalt$hashhash")
        else:
            self.running = line
        if self.honours_new_secret:
            self.password = value
        return ""


class _Conn:
    """A fresh Netmiko connection to a _Router."""

    def __init__(self, router):
        self.router = router
        self.disconnected = False

    def enable(self):
        return ""

    def send_command(self, *a, **k):
        return "hostname r2\n" + self.router.running

    def disconnect(self):
        self.disconnected = True


class _Session:
    """A stand-in for the held-open original session.

    Holding a reference to the router is what makes the push real: the line it
    accepts is the line that changes which password a later fresh login needs.
    """

    def __init__(self, fail_on=None, router=None):
        self.sent = []
        self.fail_on = fail_on or []
        self.disconnected = False
        self.router = router
        self.in_config = False

    def send_config_set(self, commands, **kw):
        out = ""
        for line in commands:
            out += self._one(line)
        return out or "ok"

    # --- the timing API push_rotation actually uses ----------------------
    #
    # send_config_set cannot answer a [confirm] prompt: it waits for a prompt
    # that never comes. The real push drives config mode by hand, so the fake
    # has to offer the same surface.

    def config_mode(self):
        self.in_config = True
        return ""

    def exit_config_mode(self):
        self.in_config = False
        return ""

    def send_command_timing(self, command, **kw):
        if command.strip() in ("", "\n"):          # answering [confirm]
            return self.router.apply("") if self.router else ""
        return self._one(command)

    def _one(self, line):
        self.sent.append(line)
        for needle in self.fail_on:
            if needle in line:
                raise RuntimeError(f"device rejected: {needle}")
        return self.router.apply(line) if self.router is not None else ""

    def send_command(self, *a, **k):
        return "clock"

    def disconnect(self):
        self.disconnected = True


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Everything around the device replaced; the sequence itself is real."""
    repo = tmp_path / "config_repo"
    (repo / ".nsot").mkdir(parents=True)

    device = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
              "username": "admin", "password": "enc", "secret": "enc"}

    router = _Router()
    state = {"router": router, "session": _Session(router=router),
             "commit_ok": True}

    # Mocked at the Netmiko boundary, NOT above it. The connection dict that
    # verify_new_credential builds is therefore exercised for real — which is
    # the whole reason this fixture exists in this shape. See
    # TestTheConnectionDict.
    import netmiko
    monkeypatch.setattr(netmiko, "ConnectHandler",
                        lambda **kw: state["router"].login(**kw))
    monkeypatch.setattr(cr, "_SLEEP", lambda _s: None)

    monkeypatch.setattr(cr, "preflight", lambda ln, hn: {
        "ok": True, "device": hn, "repo": str(repo), "device_row": device,
        "mgmt_ip": device["ip"], "identity": "uid:r2", "username": "admin",
        "privilege": "15", "current_line": ORIGINAL_LINE,
        "capture": "hostname r2\n" + ORIGINAL_LINE, "checks": [],
    })
    monkeypatch.setattr(cr, "open_original_session", lambda d: state["session"])
    monkeypatch.setattr(cr, "_commit",
                        lambda *a, **k: {"ok": state["commit_ok"],
                                         "commit": "abc123"})
    monkeypatch.setattr("modules.device.decrypt_field", lambda v: "OldPlaintext")
    state["repo"] = str(repo)
    state["device"] = device
    return state


def _fingerprint(state):
    import hashlib
    pre = cr.preflight("Lab", "r2")
    return cr.operation_fingerprint(
        device_identity=pre["identity"], username=pre["username"],
        privilege=pre["privilege"],
        capture_hash=hashlib.sha256(pre["capture"].encode()).hexdigest()[:16])


class TestTheFiveStates:
    def test_success_is_rotated_unverified_until_persistence_runs(self, wired):
        """The commit does not claim redeploy survival — persist() does."""
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.ROTATED_UNVERIFIED
        assert "survives redeploy" not in cr.summarise(result)
        assert any(s["name"] == cr.VERIFY and s["ok"] for s in result["steps"])

    def test_a_verify_failure_reverts_and_proves_it(self, wired):
        # The device stores the new secret but will not authenticate with it.
        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERTED
        assert ORIGINAL_LINE in wired["session"].sent, "the original was re-sent"
        assert "device is unchanged" in cr.summarise(result)

    def test_a_failed_revert_says_locked_out(self, wired):
        """Only this — the device ASKED and REFUSING — may claim a lockout."""
        wired["router"].dead = True
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERT_FAILED
        assert "MAY BE LOCKED OUT" in cr.summarise(result)
        assert "serial console" in cr.summarise(result)
        assert wired["router"].logins, "the device was actually asked"

    def test_a_revert_push_failure_is_still_a_lockout_risk(self, wired):
        """Device-side: the original never went back. The danger is real."""
        wired["router"].honours_new_secret = False
        wired["session"].fail_on = [ORIGINAL_PLAINTEXT]
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERT_FAILED
        assert "revert command failed" in result["reason"]
        assert "MAY BE LOCKED OUT" in cr.summarise(result)

    def test_each_revert_failure_names_its_own_cause(self, wired):
        """One state, three causes — the summary must not assert the wrong one."""
        assert "refused the original" in cr.summarise(
            {"state": cr.REVERT_FAILED, "device": "r2",
             "reason": "the device refused the original credential after the revert"})
        assert "revert command failed" in cr.summarise(
            {"state": cr.REVERT_FAILED, "device": "r2",
             "reason": "the revert command failed — recover on the console"})

    def test_a_verify_that_could_not_run_is_not_a_lockout(self, wired):
        """The r2 defect: a LOCAL fault reported as the device's verdict.

        Nothing reached the device — no socket was opened — so the one thing
        the result may not do is say the device might be lost.
        """
        wired["router"].local_fault = InvalidToken("bad Fernet ciphertext")
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERTED_UNPROVEN
        assert wired["router"].logins == [], "no connection was attempted"
        assert ORIGINAL_LINE in wired["session"].sent, "the revert still ran"
        summary = cr.summarise(result)
        assert "MAY BE LOCKED OUT" not in summary
        assert "LOCAL" in summary.upper()

    def test_a_local_fault_is_retried_while_the_session_is_open(self, wired):
        """Inconclusive is not a verdict: try again before acting on it."""
        calls = {"n": 0}
        real = wired["router"].login

        def _flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise InvalidToken("transient local fault")
            return real(**kwargs)

        wired["router"].login = _flaky
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert calls["n"] == 2, "the first attempt never reached the device"
        assert result["state"] == cr.ROTATED_UNVERIFIED

    def test_an_auth_refusal_is_not_retried(self, wired):
        """A verdict is a verdict — retrying it only delays the revert."""
        wired["router"].honours_new_secret = False
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        with_new = [k for k in wired["router"].logins
                    if k["password"] != ORIGINAL_PLAINTEXT]
        assert len(with_new) == 1, "one refusal, one attempt"

    def test_a_rejected_push_changes_nothing(self, wired):
        wired["session"] = _Session(fail_on=["algorithm-type scrypt"],
                                    router=wired["router"])
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.NOT_STARTED
        assert "device is untouched" in cr.summarise(result)

    def test_a_stale_confirmation_is_refused_before_the_push(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint="not-the-hash")

        assert result["state"] == cr.NOT_STARTED
        assert wired["session"].sent == [], "nothing may reach the device"
        assert "re-run the plan" in result["reason"]

    def test_no_original_session_means_no_push(self, wired, monkeypatch):
        """Without a revert path, the push must not happen at all."""
        def _boom(device):
            raise OSError("ssh refused")
        monkeypatch.setattr(cr, "open_original_session", _boom)

        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.NOT_STARTED
        assert "no way to revert" in result["reason"]


class TestTheStagingAndTheCacheOrdering:
    def test_the_plaintext_is_staged_before_the_push(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        names = [s["name"] for s in result["steps"]]
        assert names.index("stage") < names.index("push")

    def test_the_redaction_cache_is_invalidated_before_the_push(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        names = [s["name"] for s in result["steps"]]
        assert names.index("invalidate_redaction_cache") < names.index("push")

    def test_staging_is_cleared_on_success_and_on_revert(self, wired):
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert cr.staged_plaintext(wired["repo"], "r2") is None

        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERTED
        assert cr.staged_plaintext(wired["repo"], "r2") is None

    def test_staging_is_cleared_when_the_revert_fails(self, wired):
        """The worst outcome still leaves no password lying in the repo."""
        wired["router"].dead = True
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERT_FAILED
        assert cr.staged_plaintext(wired["repo"], "r2") is None

    def test_staging_is_cleared_when_the_verify_could_not_run(self, wired):
        wired["router"].local_fault = InvalidToken("bad ciphertext")
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERTED_UNPROVEN
        assert cr.staged_plaintext(wired["repo"], "r2") is None

    def test_a_staged_password_round_trips(self, tmp_path):
        repo = str(tmp_path)
        cr.stage_plaintext(repo, "r2", "RecoverMe123")
        assert cr.staged_plaintext(repo, "r2") == "RecoverMe123"

    def test_the_stage_file_is_owner_only(self, tmp_path):
        import os
        path = cr.stage_plaintext(str(tmp_path), "r2", "RecoverMe123")
        assert os.stat(path).st_mode & 0o777 == 0o600

    def test_the_device_must_store_a_type_9(self, wired):
        """A device that stored type 5 is not what was asked for."""
        wired["router"].stores = "5"
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERTED


class TestTheConnectionDict:
    """The r2 defect: the dict handed to Netmiko, not the verdict above it.

    The first hardware run pushed correctly, held the session correctly, and
    reverted correctly — then reported that the device might be locked out,
    because ``verify_new_credential`` built a device dict carrying a PLAINTEXT
    password and passed it to ``with_temp_connection``, which Fernet-decrypts
    whatever it is given. ``InvalidToken`` was raised before any socket opened.

    Every test here mocks at the Netmiko boundary, so the dict construction is
    exercised rather than stepped over. The old fixture replaced
    ``verify_new_credential`` wholesale, which is exactly why nothing caught it.
    """

    def test_the_new_password_reaches_netmiko_in_plaintext(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.ROTATED_UNVERIFIED

        logins = wired["router"].logins
        assert len(logins) == 1
        sent = logins[0]["password"]
        assert sent == wired["router"].password
        assert sent != wired["device"]["password"], "the stored form is ciphertext"

    def test_the_revert_verify_uses_the_decrypted_original(self, wired):
        """Decrypted once, by the caller — never handed on to decrypt again."""
        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERTED
        assert wired["router"].logins[-1]["password"] == ORIGINAL_PLAINTEXT
        assert all(k["password"] != "enc" for k in wired["router"].logins)

    def test_no_encrypted_field_is_handed_to_netmiko(self, wired):
        """`secret` is the field that made this survivable by accident."""
        wired["router"].honours_new_secret = False
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        for kwargs in wired["router"].logins:
            assert "enc" not in kwargs.values()

    def test_the_verify_path_never_touches_with_temp_connection(
            self, wired, monkeypatch):
        """The regression, stated as the rule rather than as its symptom.

        with_temp_connection() decrypts; the verify holds plaintext. Routing
        one through the other is the defect, so the path may not reach it at
        all — including on the revert.
        """
        import modules.connection as conn

        def _forbidden(*a, **k):
            raise AssertionError("the verify must not decrypt what it holds")

        monkeypatch.setattr(conn, "with_temp_connection", _forbidden)
        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERTED

    def test_the_dict_carries_what_netmiko_needs(self, wired):
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        kwargs = wired["router"].logins[0]
        assert kwargs["device_type"] == "cisco_xe"
        assert kwargs["ip"] == "203.0.113.12"
        assert kwargs["username"] == "admin"

    def test_an_auth_refusal_is_classified_as_a_device_verdict(self, wired):
        out = cr.verify_new_credential(wired["device"], "admin", "WrongOne")
        assert out["ok"] is False
        assert out["attempted"] is True, "the device answered"

    def test_a_fernet_failure_is_classified_as_a_local_fault(self, wired):
        wired["router"].local_fault = InvalidToken("bad ciphertext")
        out = cr.verify_new_credential(wired["device"], "admin", "AnyPassword")
        assert out["ok"] is False
        assert out["attempted"] is False, "nothing was asked of the device"

    def test_an_unrecognised_error_takes_the_alarming_side(self, wired):
        """The two ways to be wrong are not symmetrical.

        A false lockout warning costs a console trip. A false "local fault"
        leaves a device that may really be unreachable without one.
        """
        class SomethingNobodyListed(Exception):
            pass

        wired["router"].local_fault = SomethingNobodyListed("?")
        out = cr.verify_new_credential(wired["device"], "admin", "pw")
        assert out["attempted"] is True
        assert out["recognised"] is False

    def test_an_unrecognised_verdict_says_it_was_a_fallback(self, wired):
        class SomethingNobodyListed(Exception):
            pass

        wired["router"].local_fault = SomethingNobodyListed("?")
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERT_FAILED
        assert "UNRECOGNISED" in result["reason"]
        assert "SomethingNobodyListed" in result["reason"]

    def test_both_classifications_are_positive(self):
        """Neither answer may be reached by default alone."""
        assert cr.classify_failure("InvalidToken") == {
            "attempted": False, "recognised": True}
        assert cr.classify_failure("NetmikoAuthenticationException") == {
            "attempted": True, "recognised": True}
        assert cr.classify_failure("WhoKnows")["recognised"] is False

    def test_a_timeout_is_a_device_verdict_not_a_local_fault(self, wired):
        """Unreachable is a fact about the device; retrying it is not free."""
        class NetmikoTimeoutException(Exception):
            pass

        wired["router"].local_fault = NetmikoTimeoutException("timed out")
        out = cr.verify_new_credential(wired["device"], "admin", "AnyPassword")
        assert out["attempted"] is True


class TestTheConnectionParameters:
    """The verify must negotiate exactly like every other connection.

    Connecting directly fixed the decrypt defect and introduced a second risk:
    a second set of ConnectHandler kwargs. If they ever diverge — a legacy KEX
    or host-key algorithm for older IOS, a timeout, a device-type quirk added
    where one failure was noticed — the verify fails for a TRANSPORT reason,
    the classifier reads a connection failure as a device verdict, and a
    rotation that actually succeeded is reverted.

    The fake router cannot catch this: it models the credential exchange, not
    the negotiation. So it is pinned as a property of the parameters instead.
    """

    def test_verify_matches_the_normal_path_in_every_field_but_the_secret(self):
        from modules.connection import connection_params, stored_connection_params

        row = {"device_type": "cisco_xe", "ip": "203.0.113.12",
               "username": "admin", "password": "enc-pw", "secret": "enc-sec"}

        import modules.connection as conn
        real = conn.decrypt_field
        conn.decrypt_field = lambda v: {"enc-pw": "OldPw", "enc-sec": "OldEn"}[v]
        try:
            normal = stored_connection_params(row)
        finally:
            conn.decrypt_field = real

        verify = connection_params(dict(row, username="admin"),
                                   password="FreshPlaintext")

        assert set(normal) == set(verify), "same fields, or one path is special"
        differing = {k for k in normal if normal[k] != verify[k]}
        assert differing == {"password", "secret"}, (
            f"the verify negotiates differently in: {differing - {'password', 'secret'}}")

    def test_the_held_session_and_the_verify_use_one_builder(self):
        """Both rotation sites, not just the one that broke."""
        import inspect
        for func in (cr.open_original_session, cr.verify_new_credential):
            src = inspect.getsource(func)
            assert "connection_params" in src, f"{func.__name__} builds its own"
            assert "device_type=" not in src, f"{func.__name__} hand-rolls kwargs"

    def test_no_caller_hand_rolls_connecthandler_kwargs(self):
        """A sixth site would reintroduce exactly this divergence.

        Structural rather than textual: every ConnectHandler call on these two
        modules must take ``**params`` and name no keyword of its own.
        """
        import ast
        import io

        offenders = []
        for path in ("modules/connection.py",
                     "modules/nsot/credential_rotation.py"):
            tree = ast.parse(io.open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name != "ConnectHandler":
                    continue
                named = [k.arg for k in node.keywords if k.arg is not None]
                if named:
                    offenders.append(f"{path}:{node.lineno} names {named}")

        assert not offenders, (
            "ConnectHandler parameters built outside connection_params(): "
            + "; ".join(offenders))

    def test_connection_params_is_the_only_place_fast_cli_is_set(self):
        import ast
        import io

        tree = ast.parse(io.open("modules/connection.py", encoding="utf-8").read())
        users = [n.lineno for n in ast.walk(tree)
                 if isinstance(n, ast.Name) and n.id == "FAST_CLI"]
        assert len(users) == 1, f"FAST_CLI read at {len(users)} places: {users}"

    def test_the_secret_defaults_to_the_password(self):
        """Rotation sets both to the new value; the default must not surprise."""
        from modules.connection import connection_params
        params = connection_params(
            {"device_type": "cisco_xe", "ip": "203.0.113.12", "username": "a"},
            password="X")
        assert params["secret"] == "X"

    def test_a_plaintext_password_is_never_decrypted_by_the_builder(self):
        """The builder does not guess which kind of value it was handed."""
        from modules.connection import connection_params
        params = connection_params(
            {"device_type": "cisco_xe", "ip": "203.0.113.12", "username": "a"},
            password="Not-A-Fernet-Token")
        assert params["password"] == "Not-A-Fernet-Token"


class TestTheEnableSecretIsNotTheLoginPassword:
    """Found by the hardware probe, one config change from being a live bug.

    The rotation changes the ``username`` line and nothing else, so a device's
    enable secret is whatever it already was. Passing the NEW login password
    as ``secret`` is wrong the moment a device has a separate one — and it
    fails in the worst direction, because netmiko's ``enable()`` raises
    ``ValueError``, which the name table reads as a local fault. A rotation
    that actually succeeded would be reverted.

    No device in this fleet has an enable secret today, which is exactly why
    it passed on r2 and would have kept passing until Part 2 added one to
    close the serial-console hole.
    """

    def test_the_stored_enable_secret_is_used_not_the_new_password(self, wired):
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        kwargs = wired["router"].logins[0]
        assert kwargs["secret"] == "OldPlaintext", (
            "the verify offered the NEW password as the enable secret")
        assert kwargs["password"] != kwargs["secret"], (
            "login and enable credentials are separate things")

    def test_an_empty_enable_secret_is_passed_through_not_substituted(self):
        """Measured on r2: the stored field decrypts to "".

        The normal path passes that empty string, so this one must too. The
        property being defended is sameness, not correctness-in-isolation.
        """
        import modules.device as dev
        real = dev.decrypt_field
        dev.decrypt_field = lambda v: ""
        try:
            assert cr.enable_secret({"secret": "gAAAAAB-ciphertext"}) == ""
        finally:
            dev.decrypt_field = real

    def test_a_row_with_no_enable_secret_reuses_the_login_password(self):
        assert cr.enable_secret({"secret": ""}) is None
        assert cr.enable_secret({}) is None

        from modules.connection import connection_params
        params = connection_params(
            {"device_type": "cisco_ios", "ip": "203.0.113.12", "username": "a"},
            password="New", secret=None)
        assert params["secret"] == "New"

    def test_a_failure_after_login_is_a_device_verdict(self, wired):
        """netmiko raises ValueError from enable(). We are logged IN."""
        class _NoEnable:
            def enable(self):
                raise ValueError("Failed to enter enable mode.")

            def send_command(self, *a, **k):
                raise AssertionError("never reached")

            def disconnect(self):
                pass

        wired["router"].login = lambda **kw: _NoEnable()
        out = cr.verify_new_credential(wired["device"], "admin", "pw")

        assert out["attempted"] is True, "a login that succeeded is not local"
        assert out["recognised"] is True
        assert out["stage"] == "after_login"

    def test_a_post_login_failure_never_reads_as_a_local_fault(self, wired):
        """The classifier must not get a vote once we are authenticated."""
        assert cr.classify_failure("ValueError")["attempted"] is False
        # ...and yet:
        class _NoEnable:
            def enable(self):
                raise ValueError("Failed to enter enable mode.")

            def disconnect(self):
                pass

        wired["router"].login = lambda **kw: _NoEnable()
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        # The revert-verify hits the same broken enable, so the device really
        # did refuse — REVERT_FAILED is the honest answer. What matters is
        # that it is a DEVICE verdict either way, never REVERTED_UNPROVEN.
        assert result["state"] == cr.REVERT_FAILED
        assert result["state"] != cr.REVERTED_UNPROVEN, (
            "a device that answered must not be reported as a local fault")
        assert "UNRECOGNISED" not in result["reason"]

    def test_the_connect_stage_is_still_classified_by_name(self, wired):
        """Before a connection exists, a name is all there is."""
        wired["router"].local_fault = InvalidToken("bad ciphertext")
        out = cr.verify_new_credential(wired["device"], "admin", "pw")
        assert out["stage"] == "connect"
        assert out["attempted"] is False


class TestTheDeviceRefusesASecretOverAPassword:
    """Measured on r2, IOS-XE 17.06.01a. The reason the rotation never worked.

    Pushing a secret at a username that already holds a ``password`` entry is
    refused::

        ERROR: Can not have both a user password and a user secret.
        Please choose one or the other.

    The command is well-formed, so there is no ``% Invalid input``. The device
    declines it, keeps the old line, and the old credential goes on working.
    Every device in this fleet carries ``password 0 <x>``, so every one of
    them would have refused — r2 was not unlucky, and no amount of changing
    the password would have helped.

    ``secret 0`` without ``algorithm-type`` is refused identically, which is
    what rules out the keyword rather than the coexistence.
    """

    def test_the_old_one_command_form_is_refused(self, wired):
        """The fake now reproduces the hardware, so the old form fails here."""
        router = wired["router"]
        out = router.apply(
            "username admin privilege 15 algorithm-type scrypt secret NewPw")
        assert "Can not have both" in out
        assert router.entry == "password", "nothing changed"
        assert router.password == ORIGINAL_PLAINTEXT, "the old value survives"

    def test_the_refusal_is_not_an_invalid_input_error(self, wired):
        """Which is exactly why the old error pattern missed it."""
        out = wired["router"].apply(
            "username admin privilege 15 algorithm-type scrypt secret NewPw")
        assert "% Invalid" not in out
        assert "Incomplete" not in out

    def test_rotation_commands_removes_the_account_first(self):
        cmds = cr.rotation_commands("admin", 15, "NewPw")
        assert len(cmds) == 2
        assert cmds[0] == "no username admin"
        assert cmds[1] == ("username admin privilege 15 "
                           "algorithm-type scrypt secret NewPw")

    def test_the_masked_program_shows_the_deletion_too(self):
        """The operator confirms what is sent, including the removal."""
        masked = cr.masked_commands("admin", 15)
        assert masked[0] == "no username admin"
        assert "<generated>" in masked[1]
        assert not any("NewPw" in m for m in masked)

    def test_the_fingerprint_still_describes_the_credential(self):
        """Prefixing a deletion must not change what the operator confirms."""
        assert cr.rotation_command("admin", 15, "X") == (
            "username admin privilege 15 algorithm-type scrypt secret X")

    def test_a_full_rotation_now_lands_a_secret(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.ROTATED_UNVERIFIED
        assert wired["router"].entry == "secret"
        assert wired["router"].password != ORIGINAL_PLAINTEXT

    def test_the_old_credential_stops_working(self, wired):
        """login OLD: False on hardware. The point of the whole operation."""
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        with pytest.raises(NetmikoAuthenticationException):
            wired["router"].login(ip="203.0.113.12", username="admin",
                                  password=ORIGINAL_PLAINTEXT)


class TestTheRevertHitsTheSameRefusalMirrored:
    """After a successful push the account holds a SECRET entry.

    The original line sets a password, and the device's objection is symmetric
    — so a one-line revert is declined, and the failure the revert exists to
    recover from becomes a real lockout. Found because the fake was taught the
    device's actual rule rather than the one the command names imply.
    """

    def test_a_one_line_revert_would_be_refused(self, wired):
        router = wired["router"]
        router.entry, router.exists = "secret", True
        out = router.apply(ORIGINAL_LINE)
        assert "Can not have both" in out, "the mirrored refusal"

    def test_the_revert_removes_the_account_first(self, wired):
        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERTED
        sent = wired["session"].sent
        assert "no username admin" in sent
        assert sent.index("no username admin") < sent.index(ORIGINAL_LINE)

    def test_the_original_credential_works_again_after_the_revert(self, wired):
        wired["router"].honours_new_secret = False
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert wired["router"].entry == "password"
        assert wired["router"].login(
            ip="203.0.113.12", username="admin", password=ORIGINAL_PLAINTEXT)


class TestARefusedPushIsNotASuccessfulOne:
    """The rotation recorded a successful push of a command the device declined."""

    def test_push_rotation_raises_on_a_refusal(self, wired):
        session = _Session(router=wired["router"])
        with pytest.raises(cr.RotationRefused) as excinfo:
            cr.push_rotation(session, [
                "username admin privilege 15 algorithm-type scrypt secret X"])
        assert "Can not have both" in str(excinfo.value)

    def test_a_refused_push_leaves_the_device_untouched(self, wired):
        wired["session"] = _Session(router=wired["router"])
        # Force the old, refused shape through the real rotate() path.
        import modules.nsot.credential_rotation as mod
        original = mod.rotation_commands
        mod.rotation_commands = lambda u, p, pw: [
            f"username {u} privilege {p} algorithm-type scrypt secret {pw}"]
        try:
            result = cr.rotate("Lab", "r2",
                               confirmed_fingerprint=_fingerprint(wired))
        finally:
            mod.rotation_commands = original

        assert result["state"] == cr.NOT_STARTED
        assert "Can not have both" in result["reason"]
        assert wired["router"].entry == "password"
        assert cr.staged_plaintext(wired["repo"], "r2") is None

    def test_only_the_current_output_can_trigger_a_confirm_answer(self, wired):
        """Found in a hardware transcript: a second, unasked-for Enter.

        The check searched the ACCUMULATED transcript, so the `no username`
        prompt was still in range after the next command and was answered
        twice. Harmless at a config prompt, and exactly the stray keystroke
        that gets eaten as the answer to some later prompt.
        """
        session = _Session(router=wired["router"])
        cr.push_rotation(session, cr.rotation_commands("admin", 15, "NewPw"))

        blanks = [c for c in session.sent if c.strip() == ""]
        assert len(blanks) == 0, (
            f"answers are sent via send_command_timing, not recorded as "
            f"commands; got {blanks}")
        assert wired["router"].entry == "secret"

    def test_a_second_command_is_not_eaten_as_the_confirm_answer(self, wired):
        """If the prompt consumed it, the account would be absent, not secret."""
        session = _Session(router=wired["router"])
        cr.push_rotation(session, cr.rotation_commands("admin", 15, "NewPw"))
        assert wired["router"].exists is True
        assert wired["router"].entry == "secret"

    def test_push_rotation_answers_the_confirm_prompt(self, wired):
        """An unanswered [confirm] leaves the session mid-dialogue."""
        session = _Session(router=wired["router"])
        cr.push_rotation(session, cr.rotation_commands("admin", 15, "NewPw"))
        assert wired["router"].awaiting_confirm is False
        assert wired["router"].entry == "secret"

    def test_the_error_pattern_matches_the_real_refusal(self):
        import re
        from modules.pipeline import IOS_ERROR_PATTERN

        real = ("R2(config)#username admin privilege 15 algorithm-type scrypt "
                "secret X\n"
                "ERROR: Can not have both a user password and a user secret.\n"
                "Please choose one or the other.\n")
        assert re.search(IOS_ERROR_PATTERN, real)
        assert re.search(IOS_ERROR_PATTERN,
                         "% Invalid input detected at '^' marker.")

    def test_the_error_pattern_does_not_fire_on_echoed_config(self):
        """Netmiko echoes commands after the prompt, so only output starts a line."""
        import re
        from modules.pipeline import IOS_ERROR_PATTERN

        for benign in (
            "R2(config-if)#description ERROR: link flaps under load",
            "R2(config)#banner motd ^C report any ERROR: to noc ^C",
            "R2(config)#ip access-list extended ERROR-DROP",
            "R2(config)#username x privilege 15 secret Ab%Errors",
        ):
            assert not re.search(IOS_ERROR_PATTERN, benign), benign


class TestTheChainMakesOxidizedRereadRouterDb:
    """The defect that stranded r2: writing router.db is not enough.

    Measured on Oxidized 0.37.0 with the CORRECT credential already in the
    file: every fetch failed AuthenticationFailed, GET /reload did not change
    that, and a container restart made the very next fetch succeed. Net::SSH
    from inside the container authenticated with that same row throughout,
    under Oxidized's own option set — so the credential was never wrong. A
    live node object holds its credential in memory.

    The chain had no reload step at all, so `confirm_fetch` was always polling
    an Oxidized that could not have picked the change up.
    """

    BASE = dict(mgmt_ip="203.0.113.12", username="admin", password="pw",
                hostname="r2", new_hash="9 $9$salt$hash",
                after_iso="2026-09-21 08:00:00")

    def test_the_reload_stage_runs_between_the_write_and_the_fetch(self, monkeypatch):
        order = []
        monkeypatch.setattr(cr, "update_oxidized_row",
                            lambda *a, **k: order.append("write") or {"ok": True})
        monkeypatch.setattr(cr, "reload_oxidized",
                            lambda **k: order.append("reload") or {"ok": True})
        monkeypatch.setattr(cr, "confirm_fetch",
                            lambda *a, **k: order.append("fetch") or {"ok": True})
        monkeypatch.setattr(cr, "run_sync", lambda **k: {"ok": True})
        monkeypatch.setattr(cr, "verify_startup_file",
                            lambda *a, **k: {"ok": True, "matches": 1})

        cr.persist({"device": "r2", "state": cr.ROTATED_UNVERIFIED, "steps": []},
                   **self.BASE)
        assert order == ["write", "reload", "fetch"], (
            "a fetch before the reload polls an Oxidized holding the old "
            "credential")

    def test_a_failed_reload_stops_before_the_fetch(self, monkeypatch):
        """Otherwise the fetch fails for a reason that looks nothing like it."""
        monkeypatch.setattr(cr, "update_oxidized_row", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "reload_oxidized",
                            lambda **k: {"ok": False, "error": "no such container"})
        called = []
        monkeypatch.setattr(cr, "confirm_fetch",
                            lambda *a, **k: called.append(1) or {"ok": True})

        out = cr.persist({"device": "r2", "state": cr.ROTATED_UNVERIFIED,
                          "steps": []}, **self.BASE)
        assert called == []
        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert [s["name"] for s in out["persistence"]][-1] == "oxidized_reload"

    def test_reload_without_a_command_reports_itself_unverified(self, monkeypatch):
        """The /reload-only path is the one measured NOT to work."""
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: {"oxidized_rest_url": "http://x",
                                               "oxidized_reload_command": ""}.get(k, d))
        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("no")))

        out = cr.reload_oxidized()
        assert out["verified"] is False
        assert out["mechanism"] == "rest_reload_only"

    def test_a_restart_is_not_ok_until_the_api_answers(self, monkeypatch):
        """A queued fetch against a restarting Oxidized goes nowhere."""
        import subprocess
        import urllib.request
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: {"oxidized_rest_url": "http://x",
                                               "oxidized_reload_command": "true"}.get(k, d))
        monkeypatch.setattr(subprocess, "run",
                            lambda *a, **k: type("P", (), {"returncode": 0,
                                                           "stdout": "", "stderr": ""})())
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("down")))

        out = cr.reload_oxidized(timeout=0.01, sleep=lambda _s: None)
        assert out["ok"] is False
        assert "did not answer" in out["error"]


class TestPersistenceNeverReverts:
    BASE = dict(mgmt_ip="203.0.113.12", username="admin", password="pw",
                hostname="r2", new_hash="9 $9$salt$hash",
                after_iso="2026-09-21 08:00:00")

    def _result(self):
        return {"device": "r2", "state": cr.ROTATED_UNVERIFIED, "steps": []}

    def test_a_router_db_failure_leaves_the_device_rotated(self, monkeypatch):
        monkeypatch.setattr(cr, "update_oxidized_row",
                            lambda *a, **k: {"ok": False, "error": "no sudo"})
        out = cr.persist(self._result(), **self.BASE)

        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert out["persistence"][0]["ok"] is False
        assert "ROTATED and committed" in cr.summarise(out)
        # The message must be TERMINAL: the process has exited by the time it
        # is printed, so nothing is retrying and it must not say otherwise.
        assert "Retrying" not in cr.summarise(out)
        assert "Nothing is retrying" in cr.summarise(out)

    def test_a_fetch_failure_leaves_the_device_rotated(self, monkeypatch):
        monkeypatch.setattr(cr, "update_oxidized_row", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "reload_oxidized",
                            lambda **k: {"ok": True, "mechanism": "restart",
                                         "verified": True})
        monkeypatch.setattr(cr, "confirm_fetch",
                            lambda *a, **k: {"ok": False, "error": "timeout"})
        out = cr.persist(self._result(), **self.BASE)

        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert [s["name"] for s in out["persistence"]] == \
            ["oxidized_row", "oxidized_reload", "fetch_confirmed"]

    def test_a_startup_file_miss_leaves_the_device_rotated(self, monkeypatch):
        monkeypatch.setattr(cr, "update_oxidized_row", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "reload_oxidized",
                            lambda **k: {"ok": True, "mechanism": "restart",
                                         "verified": True})
        monkeypatch.setattr(cr, "confirm_fetch", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "run_sync", lambda **k: {"ok": True})
        monkeypatch.setattr(cr, "verify_startup_file",
                            lambda *a, **k: {"ok": False, "matches": 0})
        out = cr.persist(self._result(), **self.BASE)

        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert "redeploy would boot the OLD password" in cr.summarise(out)

    def test_the_full_chain_reaches_persisted(self, monkeypatch):
        monkeypatch.setattr(cr, "update_oxidized_row", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "reload_oxidized",
                            lambda **k: {"ok": True, "mechanism": "restart",
                                         "verified": True})
        monkeypatch.setattr(cr, "confirm_fetch", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "run_sync", lambda **k: {"ok": True})
        monkeypatch.setattr(cr, "verify_startup_file",
                            lambda *a, **k: {"ok": True, "matches": 1})
        out = cr.persist(self._result(), **self.BASE)

        assert out["state"] == cr.ROTATED_PERSISTED
        assert "survives redeploy" in cr.summarise(out)

    def test_persist_never_touches_the_device(self):
        """Structural: nothing in the chain can send a command."""
        import inspect
        source = inspect.getsource(cr.persist)
        for forbidden in ("push_rotation", "_revert", "open_original_session",
                          "send_config_set"):
            assert forbidden not in source, forbidden

    def test_confirm_fetch_requires_success_AFTER_the_rotation(self, monkeypatch):
        """A stale success is not a fetch of the new config."""
        import json

        class _Resp:
            def __init__(self, payload):
                self._p = json.dumps(payload).encode()
            def read(self):
                return self._p
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        stale = [{"name": "203.0.113.12",
                  "last": {"status": "success", "end": "2026-09-21 07:00:00 UTC"}}]
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp(stale))
        monkeypatch.setattr(cr, "_setting_rest", None, raising=False)

        out = cr.confirm_fetch("203.0.113.12", "2026-09-21 08:00:00",
                               attempts=2, base_delay=0, rest="http://x",
                               sleep=lambda s: None)
        assert out["ok"] is False
        assert "no successful fetch after the rotation" in out["error"]


class TestRotateCarriesWhatPersistNeeds:
    """persist() must not re-read the device to find the hash.

    The hash that matters is the one the VERIFY saw — re-deriving it from a
    later capture would ask the device again and could pick up a different
    answer, which defeats the point of having verified.
    """

    def test_the_verified_hash_is_carried(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["new_hash"].startswith("9 $9$")
        assert result["repo"]
        assert result["mgmt_ip"] == "203.0.113.12"
        assert result["username"] == "admin"

    def test_nothing_is_carried_when_the_rotation_did_not_happen(self, wired):
        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert "new_hash" not in result
        assert result["state"] == cr.REVERTED


class TestTheInteractiveScript:
    """The confirm lives in the script because the HTTP gates do not apply."""

    SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "scripts", "nmas-rotate-credential")

    def test_it_refuses_a_non_interactive_stdin(self):
        """A typed confirmation that can be piped in is not a confirmation."""
        import subprocess
        import sys

        proc = subprocess.run([sys.executable, self.SCRIPT, "--device", "r2"],
                              input="r2\n", capture_output=True, text=True)
        assert proc.returncode == 2
        assert "not a terminal" in proc.stderr

    def test_it_requires_the_exact_hostname(self):
        source = open(self.SCRIPT, encoding="utf-8").read()
        assert 'typed != device' in source
        assert "Nothing was sent" in source

    def test_it_records_a_distinct_actor_kind(self):
        """A local CLI session is not Access-verified, and must not look like it."""
        source = open(self.SCRIPT, encoding="utf-8").read()
        assert 'actor_kind="person_cli"' in source
        assert '"access_verified": False' in source
        assert "NOT Access-verified" in source

    def test_it_states_why_the_confirm_is_in_the_script(self):
        doc = open(self.SCRIPT, encoding="utf-8").read()
        assert "does not pass through them" in doc
        assert "bypass the gate" in doc
