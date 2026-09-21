"""Credential rotation: generation, the confirm fingerprint, and the states.

The states matter most. "Did it work" has five answers here, and two of them
are easy to conflate in a way that destroys a completed change: a device that
rotated but whose new password has not reached the startup file is **rotated**,
and reverting it to fix that would undo real work to solve a bookkeeping
problem.
"""

import math

import pytest

from modules.nsot import credential_rotation as cr


class TestGeneration:
    def test_length_and_entropy(self):
        assert cr.LENGTH == 32
        assert len(cr.CHARSET) == 79
        assert 32 * math.log2(79) > 200

    def test_the_charset_excludes_what_the_cli_would_eat(self):
        for ch in "? \"'\\`|":
            assert ch not in cr.CHARSET, ch

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
        assert "redeploy would restore the old password" in summary

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

    def test_only_the_verify_step_is_named_as_reverting(self):
        """Documented in one place so the rule cannot drift."""
        import inspect
        assert cr.VERIFY == "verify_new_credential"
        assert "Only :data:`VERIFY` failing reverts" in inspect.getdoc(cr)
