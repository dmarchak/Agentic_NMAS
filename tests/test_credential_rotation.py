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


class _Session:
    """A stand-in for the held-open original session."""

    def __init__(self, fail_on=None):
        self.sent = []
        self.fail_on = fail_on or []
        self.disconnected = False

    def send_config_set(self, commands, **kw):
        self.sent.extend(commands)
        for needle in self.fail_on:
            if any(needle in c for c in commands):
                raise RuntimeError(f"device rejected: {needle}")
        return "ok"

    def send_command(self, *a, **k):
        return "clock"

    def disconnect(self):
        self.disconnected = True


ORIGINAL_LINE = "username admin privilege 15 password OldPlaintext"
POST_CONFIG = "username admin privilege 15 secret 9 $9$saltsalt$hashhash"


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Everything around the device replaced; the sequence itself is real."""
    repo = tmp_path / "config_repo"
    (repo / ".nsot").mkdir(parents=True)

    device = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
              "username": "admin", "password": "enc", "secret": "enc"}

    state = {"session": _Session(), "verify": [], "commit_ok": True}

    monkeypatch.setattr(cr, "preflight", lambda ln, hn: {
        "ok": True, "device": hn, "repo": str(repo), "device_row": device,
        "mgmt_ip": device["ip"], "identity": "uid:r2", "username": "admin",
        "privilege": "15", "current_line": ORIGINAL_LINE,
        "capture": "hostname r2\n" + ORIGINAL_LINE, "checks": [],
    })
    monkeypatch.setattr(cr, "open_original_session", lambda d: state["session"])
    monkeypatch.setattr(cr, "verify_new_credential",
                        lambda d, u, p: state["verify"].pop(0))
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
        wired["verify"] = [{"ok": True, "config": POST_CONFIG}]
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.ROTATED_UNVERIFIED
        assert "survives redeploy" not in cr.summarise(result)
        assert any(s["name"] == cr.VERIFY and s["ok"] for s in result["steps"])

    def test_a_verify_failure_reverts_and_proves_it(self, wired):
        wired["verify"] = [
            {"ok": False, "error": "auth failed"},     # the new credential
            {"ok": True, "config": ORIGINAL_LINE},     # the revert proof
        ]
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERTED
        assert ORIGINAL_LINE in wired["session"].sent, "the original was re-sent"
        assert "device is unchanged" in cr.summarise(result)

    def test_a_failed_revert_says_locked_out(self, wired):
        wired["verify"] = [
            {"ok": False, "error": "auth failed"},
            {"ok": False, "error": "auth failed again"},
        ]
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERT_FAILED
        assert "MAY BE LOCKED OUT" in cr.summarise(result)
        assert "serial console" in cr.summarise(result)

    def test_a_rejected_push_changes_nothing(self, wired):
        wired["session"] = _Session(fail_on=["algorithm-type scrypt"])
        wired["verify"] = []
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.NOT_STARTED
        assert "device is untouched" in cr.summarise(result)

    def test_a_stale_confirmation_is_refused_before_the_push(self, wired):
        wired["verify"] = []
        result = cr.rotate("Lab", "r2", confirmed_fingerprint="not-the-hash")

        assert result["state"] == cr.NOT_STARTED
        assert wired["session"].sent == [], "nothing may reach the device"
        assert "re-run the plan" in result["reason"]

    def test_no_original_session_means_no_push(self, wired, monkeypatch):
        """Without a revert path, the push must not happen at all."""
        def _boom(device):
            raise OSError("ssh refused")
        monkeypatch.setattr(cr, "open_original_session", _boom)
        wired["verify"] = []

        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.NOT_STARTED
        assert "no way to revert" in result["reason"]


class TestTheStagingAndTheCacheOrdering:
    def test_the_plaintext_is_staged_before_the_push(self, wired):
        wired["verify"] = [{"ok": True, "config": POST_CONFIG}]
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        names = [s["name"] for s in result["steps"]]
        assert names.index("stage") < names.index("push")

    def test_the_redaction_cache_is_invalidated_before_the_push(self, wired):
        wired["verify"] = [{"ok": True, "config": POST_CONFIG}]
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        names = [s["name"] for s in result["steps"]]
        assert names.index("invalidate_redaction_cache") < names.index("push")

    def test_staging_is_cleared_on_success_and_on_revert(self, wired):
        wired["verify"] = [{"ok": True, "config": POST_CONFIG}]
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert cr.staged_plaintext(wired["repo"], "r2") is None

        wired["verify"] = [{"ok": False, "error": "x"},
                           {"ok": True, "config": ORIGINAL_LINE}]
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
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
        wired["verify"] = [
            {"ok": True, "config": "username admin privilege 15 secret 5 $1$x$y"},
            {"ok": True, "config": ORIGINAL_LINE},
        ]
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERTED


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

    def test_a_fetch_failure_leaves_the_device_rotated(self, monkeypatch):
        monkeypatch.setattr(cr, "update_oxidized_row", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "confirm_fetch",
                            lambda *a, **k: {"ok": False, "error": "timeout"})
        out = cr.persist(self._result(), **self.BASE)

        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert [s["name"] for s in out["persistence"]] == \
            ["oxidized_row", "fetch_confirmed"]

    def test_a_startup_file_miss_leaves_the_device_rotated(self, monkeypatch):
        monkeypatch.setattr(cr, "update_oxidized_row", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "confirm_fetch", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "run_sync", lambda **k: {"ok": True})
        monkeypatch.setattr(cr, "verify_startup_file",
                            lambda *a, **k: {"ok": False, "matches": 0})
        out = cr.persist(self._result(), **self.BASE)

        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert "redeploy would restore the old password" in cr.summarise(out)

    def test_the_full_chain_reaches_persisted(self, monkeypatch):
        monkeypatch.setattr(cr, "update_oxidized_row", lambda *a, **k: {"ok": True})
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
        wired["verify"] = [{"ok": True, "config": POST_CONFIG}]
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["new_hash"].startswith("9 $9$")
        assert result["repo"]
        assert result["mgmt_ip"] == "203.0.113.12"
        assert result["username"] == "admin"

    def test_nothing_is_carried_when_the_rotation_did_not_happen(self, wired):
        wired["verify"] = [{"ok": False, "error": "x"},
                           {"ok": True, "config": ORIGINAL_LINE}]
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
