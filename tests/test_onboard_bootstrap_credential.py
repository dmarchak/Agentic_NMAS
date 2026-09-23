"""Stage 4C.2 — the one-time bootstrap credential, and the crash window.

**Between the device booting with this value and the rotation replacing it,
it is the only way in.** If it existed only in memory, a wizard crash in that
interval would leave a reachable device nobody can log into — tolerable for a
probe, not for r6.

That is the *same* window `credential_rotation` already covers, between the
device accepting a password and the credential store being written. So this
uses **its** staging rather than a second mechanism: same directory, same
encryption, same modes, same recovery path. Two mechanisms for one window is
how one of them stops being maintained.

And a run whose rotation failed **does not report success** — the
`mark_done()` rule. An operator told "onboarded" walks away from a device
still holding a throwaway password.
"""

import os

import pytest


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.secrets_store.KEY_FILE",
                        str(tmp_path / "key.key"))
    monkeypatch.setattr("modules.secrets_store._fernet", None)
    return str(tmp_path / "config_repo")


class TestTheCredentialItself:

    def test_two_runs_differ(self):
        """Not a smoke test: 50 mints, all distinct."""
        from modules.nsot.onboard import mint_bootstrap_credential

        values = {mint_bootstrap_credential() for _ in range(50)}
        assert len(values) == 50

    def test_it_uses_secrets_not_random(self):
        """This is the only credential the device has for part of its life."""
        import inspect

        from modules.nsot import onboard

        src = inspect.getsource(onboard.mint_bootstrap_credential)
        assert "secrets.choice" in src
        assert "random." not in src

    def test_it_has_no_look_alike_characters(self):
        """The one time anybody reads this value is when something has gone
        wrong and they are typing it into a console."""
        from modules.nsot.onboard import mint_bootstrap_credential

        for _ in range(20):
            assert not (set(mint_bootstrap_credential()) & set("0O1lI"))

    def test_it_cannot_break_the_files_it_lives_in(self):
        """It reaches a config file, a console, and possibly `router.db`,
        which is colon-delimited — `nmas-oxidized-cred` refuses a colon."""
        from modules.nsot.onboard import mint_bootstrap_credential

        for _ in range(20):
            value = mint_bootstrap_credential()
            assert value.isascii() and value.isalnum()
            assert not (set(value) & set(":\n'\"$`\\ "))

    def test_it_is_long_enough_that_guessing_is_not_the_attack(self):
        from modules.nsot.onboard import BOOTSTRAP_LENGTH

        assert BOOTSTRAP_LENGTH >= 20


class TestItSurvivesTheCrashWindow:
    """The property this step exists for."""

    def test_a_staged_credential_is_recoverable(self, repo):
        from modules.nsot import onboard

        secret = onboard.mint_bootstrap_credential()
        onboard.stage_bootstrap_credential(repo, "bp-onboard-c", secret)
        assert onboard.staged_bootstrap_credential(repo, "bp-onboard-c") == secret

    def test_it_survives_a_process_that_never_returns(self, repo):
        """The wizard is killed between boot and rotation. Modelled as: the
        value is staged and then nothing else happens — no clear, no rotate.
        A fresh reader must still find it."""
        from modules.nsot import onboard

        secret = onboard.mint_bootstrap_credential()
        onboard.stage_bootstrap_credential(repo, "bp-onboard-c", secret)

        # A "new process": nothing in memory, only the file.
        del secret
        recovered = onboard.staged_bootstrap_credential(repo, "bp-onboard-c")
        assert recovered and len(recovered) >= 20

    def test_it_is_encrypted_on_disk(self, repo):
        from modules.nsot import onboard
        from modules.secrets_store import is_encrypted

        onboard.stage_bootstrap_credential(repo, "bp", "PLAINTEXTVALUE123")
        path = os.path.join(repo, ".nsot/staging/credential", "bp.enc")
        body = open(path, encoding="utf-8").read()
        assert "PLAINTEXTVALUE123" not in body
        assert is_encrypted(body.strip())

    @pytest.mark.skipif(os.name == "nt", reason="chmod is a no-op on Windows")
    def test_the_staging_file_is_owner_only(self, repo):
        import stat

        from modules.nsot import onboard

        onboard.stage_bootstrap_credential(repo, "bp", "x")
        path = os.path.join(repo, ".nsot/staging/credential", "bp.enc")
        assert not (stat.S_IMODE(os.stat(path).st_mode) & 0o077)

    def test_nothing_staged_reads_as_none(self, repo):
        """Absent and empty must not be confused."""
        from modules.nsot import onboard

        assert onboard.staged_bootstrap_credential(repo, "never-staged") is None


class TestOneMechanismNotTwo:
    """Two mechanisms for one window is how one of them stops being
    maintained."""

    def test_it_delegates_to_the_rotations_staging(self):
        from tests.astcheck import calls_in

        from modules.nsot import onboard

        assert calls_in(onboard.stage_bootstrap_credential, "stage_plaintext") == 1
        assert calls_in(onboard.staged_bootstrap_credential, "staged_plaintext") == 1
        assert calls_in(onboard.clear_bootstrap_credential, "clear_staged") == 1

    def test_it_writes_to_the_rotations_directory(self, repo):
        from modules.nsot import onboard
        from modules.nsot.credential_rotation import STAGING_REL

        path = onboard.stage_bootstrap_credential(repo, "bp", "x")
        assert STAGING_REL.replace("/", os.sep) in path

    def test_onboard_does_not_define_its_own_staging_path(self):
        """A second constant is a second mechanism wearing one name."""
        import inspect

        from modules.nsot import onboard

        src = inspect.getsource(onboard)
        assert "staging/credential" not in src.replace(
            "credential_rotation", "")


class TestAFailedRotationDoesNotReportSuccess:
    """The `mark_done()` rule. An operator told "onboarded" walks away from a
    device still holding a throwaway password."""

    def _finish(self, repo, result_or_exc):
        from modules.nsot import onboard

        def _rotate(list_name, hostname, **kw):
            if isinstance(result_or_exc, Exception):
                raise result_or_exc
            return result_or_exc

        return onboard.finish_bootstrap(repo, "bp", "probe",
                                        confirmed_fingerprint="abc",
                                        rotate=_rotate)

    def test_a_successful_rotation_clears_the_staged_value(self, repo):
        from modules.nsot import onboard
        from modules.nsot.credential_rotation import ROTATED_PERSISTED

        onboard.stage_bootstrap_credential(repo, "bp", "x")
        out = self._finish(repo, {"state": ROTATED_PERSISTED})
        assert out["rotated"] is True
        assert onboard.staged_bootstrap_credential(repo, "bp") is None

    def test_a_failed_rotation_says_not_rotated(self, repo):
        from modules.nsot import onboard
        from modules.nsot.credential_rotation import NOT_STARTED

        onboard.stage_bootstrap_credential(repo, "bp", "x")
        out = self._finish(repo, {"state": NOT_STARTED, "error": "no route"})
        assert out["rotated"] is False
        assert "no route" in out["reason"]

    def test_a_failed_rotation_keeps_the_credential(self, repo):
        """Clearing it on failure would close the crash window by throwing
        away the thing that makes it survivable."""
        from modules.nsot import onboard
        from modules.nsot.credential_rotation import NOT_STARTED

        onboard.stage_bootstrap_credential(repo, "bp", "keep-me-please")
        out = self._finish(repo, {"state": NOT_STARTED})
        assert out["recoverable"] is True
        assert onboard.staged_bootstrap_credential(repo, "bp") == "keep-me-please"

    def test_a_raising_rotation_is_a_failure_not_a_crash(self, repo):
        from modules.nsot import onboard

        onboard.stage_bootstrap_credential(repo, "bp", "keep-me")
        out = self._finish(repo, RuntimeError("ssh died"))
        assert out["rotated"] is False
        assert "ssh died" in out["reason"]
        assert onboard.staged_bootstrap_credential(repo, "bp") == "keep-me"

    def test_rotated_but_persistence_unfinished_is_still_rotated(self, repo):
        """Two of the five states mean the DEVICE is rotated and the
        bookkeeping is not finished — a success for the credential and a
        finding for the operator. A truthiness check would collapse that."""
        from modules.nsot import onboard
        from modules.nsot.credential_rotation import ROTATED_UNVERIFIED

        onboard.stage_bootstrap_credential(repo, "bp", "x")
        out = self._finish(repo, {"state": ROTATED_UNVERIFIED})
        assert out["rotated"] is True
        assert out["state"] == ROTATED_UNVERIFIED

    def test_it_uses_rotation_succeeded_not_a_truthiness_check(self):
        """There is no `ok` key on a rotation result, and reading one would
        have made every rotation look failed."""
        from tests.astcheck import calls_in, code_of

        from modules.nsot import onboard

        assert calls_in(onboard.finish_bootstrap, "rotation_succeeded") == 1
        assert '"ok"' not in code_of(onboard.finish_bootstrap)

    def test_the_confirm_is_passed_through_not_invented(self):
        """The rotation is a device change and its confirm is the wizard's.
        A default here would be this layer confirming for the operator."""
        import inspect

        from modules.nsot import onboard

        param = inspect.signature(onboard.finish_bootstrap).parameters[
            "confirmed_fingerprint"]
        assert param.default is inspect.Parameter.empty


class TestItIsNeverADurableCredential:

    def test_the_plan_does_not_carry_it(self):
        import dataclasses

        from modules.nsot.onboard import OnboardPlan

        assert "secret" not in {f.name for f in dataclasses.fields(OnboardPlan)}

    def test_onboard_never_writes_the_devices_csv_with_it(self):
        from tests.astcheck import calls_in

        from modules.nsot import onboard

        for name in dir(onboard):
            fn = getattr(onboard, name, None)
            if callable(fn) and getattr(fn, "__module__", "") == onboard.__name__:
                assert calls_in(fn, "write_devices_csv") == 0, name

    def test_the_credential_store_override_is_written_and_then_replaced(self):
        """Corrected in 4C.7, and the correction matters.

        This asserted that **nothing** in `onboard.py` calls
        `set_device_override`. That was too strong: the bootstrap credential
        HAS to reach the credential store, or `load_saved_devices()` cannot
        resolve credentials for the device and nothing — the connection pool,
        the capture, drift — can reach it.

        The agreed property is *never a **durable** credential*, and durable
        is what rotation ends. So: exactly one writer, and `finish_bootstrap`
        replaces it.
        """
        from tests.astcheck import calls_in

        from modules.nsot import onboard

        writers = [name for name in dir(onboard)
                   if callable(getattr(onboard, name, None))
                   and getattr(getattr(onboard, name), "__module__", "")
                   == onboard.__name__
                   and calls_in(getattr(onboard, name), "set_device_override")]
        assert writers == ["bind_credentials_step"], writers

    def test_it_is_staged_before_the_store_is_written(self):
        """A crash between the two would leave a credential in the store and
        nothing able to recover it — the staging file is what makes the
        window survivable, so it comes first."""
        from tests.astcheck import code_of

        from modules.nsot import onboard

        src = code_of(onboard.bind_credentials_step)
        assert (src.index("stage_bootstrap_credential")
                < src.index("set_device_override"))

    def test_nothing_writes_it_to_the_devices_csv(self):
        from tests.astcheck import calls_in

        from modules.nsot import onboard

        for name in dir(onboard):
            fn = getattr(onboard, name, None)
            if callable(fn) and getattr(fn, "__module__", "") == onboard.__name__:
                assert calls_in(fn, "write_devices_csv") == 0, name


class TestTheOverrideIsWhereTheResolverLooks:
    """`bind_credentials_step` wrote the override under the wrong key, with
    the wrong values, and `/onboard/create` failed at its first step every
    time it ran.

        set_device_override(device_key, username, password, secret="")
        set_device_override(plan.list_name, plan.hostname, {...})

    A list name where the key belongs, a hostname where the username
    belongs, a dict where a string belongs. `encrypt_value(dict)` raises
    AttributeError.

    **So this asserts the property, not the call shape.** A test that
    compared arguments would have been written from the same misreading as
    the call. What matters is that the credential the device will boot with
    is the one the resolver hands back for that device — which is what phase
    2 depends on, and the only reason the override is written at all.
    """

    def test_the_minted_secret_comes_back_from_resolve(self, tmp_path,
                                                       monkeypatch):
        import modules.credentials as creds
        from modules.nsot import onboard

        store = tmp_path / "creds.json"
        monkeypatch.setattr(creds, "_FILE", str(store))

        repo = tmp_path / "config_repo"
        repo.mkdir()
        plan = onboard.build_plan("bp1", "cisco_iosxe", "probe",
                                  mgmt_ip="203.0.113.31",
                                  mgmt_mask="255.255.255.0",
                                  manager_interface="GigabitEthernet2")
        secret = onboard.bind_credentials_step(plan, repo=str(repo))

        got = creds.resolve("203.0.113.31")
        assert got["ok"] is True, got
        assert got["source"] == "device-override"
        assert got["username"] == "admin"
        assert got["password"] == secret
        assert got["secret"] == secret

    def test_it_is_not_keyed_on_the_list_name(self, tmp_path, monkeypatch):
        """The exact wrong key, named — so the defect cannot come back under
        a different spelling of the same mistake."""
        import modules.credentials as creds
        from modules.nsot import onboard

        monkeypatch.setattr(creds, "_FILE", str(tmp_path / "creds.json"))
        repo = tmp_path / "config_repo"
        repo.mkdir()
        plan = onboard.build_plan("bp1", "cisco_iosxe", "probe",
                                  mgmt_ip="203.0.113.31",
                                  mgmt_mask="255.255.255.0",
                                  manager_interface="GigabitEthernet2")
        onboard.bind_credentials_step(plan, repo=str(repo))

        assert not creds.has_device_override("probe")
        assert creds.has_device_override("203.0.113.31")

    def test_the_step_does_not_raise(self, tmp_path, monkeypatch):
        """It raised AttributeError, so the run failed at step one. The
        control for the two tests above: they would both pass against a step
        that stored nothing if the assertions were only about absence."""
        import modules.credentials as creds
        from modules.nsot import onboard

        monkeypatch.setattr(creds, "_FILE", str(tmp_path / "creds.json"))
        repo = tmp_path / "config_repo"
        repo.mkdir()
        plan = onboard.build_plan("bp1", "cisco_iosxe", "probe",
                                  mgmt_ip="203.0.113.31",
                                  mgmt_mask="255.255.255.0",
                                  manager_interface="GigabitEthernet2")
        secret = onboard.bind_credentials_step(plan, repo=str(repo))
        assert secret and len(secret) >= 16
