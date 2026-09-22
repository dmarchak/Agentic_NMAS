"""A two-valued check on a remote system can pass by not asking.

Found on the D2 probe. The redeploy checklist's item 5 read:

    sshpass -p 'admin' ssh ... && echo "FAIL: old credential works" \\
                               || echo "PASS: admin refused"

The connection failed at **key exchange** -- a modern OpenSSH against a 2018
vIOS image -- so `ssh` exited non-zero and the line printed PASS. It would
print PASS with the device powered off. On the production redeploy it would
have printed PASS while every router sat on `admin/admin` and unreachable --
the precise hazard the stage exists to detect, reported as absent.

Exit status conflates "the device refused us" with "we never reached the
device". Those have opposite consequences, so they cannot share a verdict.

The second correction matters more than the third value: the check connects
**the way NMAS does**, through `connection_params()` and Netmiko, rather than
through the shell's `ssh`. The claim is "NMAS can log in", and the shell's
client negotiates differently -- which is what produced the false PASS.
"""

import pytest

from tests.nmas_check_credential import (ACCEPTED, INCONCLUSIVE, REFUSED,
                                         check)

ROW = {"hostname": "r1", "ip": "203.0.113.1", "username": "admin",
       "password": "enc", "secret": "enc", "device_type": "cisco_ios"}


@pytest.fixture
def world(monkeypatch):
    state = {"result": {"ok": True, "stage": "after_login"}}
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path: [ROW])
    monkeypatch.setattr("modules.device.decrypt_field", lambda v: "stored-pw")
    monkeypatch.setattr("modules.nsot.credential_rotation.enable_secret",
                        lambda row: "en")
    monkeypatch.setattr("modules.nsot.credential_rotation.verify_new_credential",
                        lambda row, user, pw, secret=None: state["result"])
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: type("R", (), {
                            "name": "Default", "csv_path": "/x/devices.csv"})())
    return state


class TestTheThreeVerdicts:
    def test_a_successful_login_is_accepted(self, world):
        assert check("Default", "r1")["verdict"] == ACCEPTED

    def test_a_device_saying_no_is_refused(self, world):
        world["result"] = {"ok": False, "attempted": True,
                           "error": "Authentication failed",
                           "error_type": "NetmikoAuthenticationException",
                           "stage": "connect"}
        assert check("Default", "r1")["verdict"] == REFUSED

    def test_never_reaching_the_device_is_INCONCLUSIVE(self, world):
        """The case that produced the false PASS."""
        world["result"] = {"ok": False, "attempted": False,
                           "error": "no matching key exchange method",
                           "error_type": "SSHException", "stage": "connect"}
        assert check("Default", "r1")["verdict"] == INCONCLUSIVE

    def test_inconclusive_is_not_refused(self, world):
        """The whole point. A shell exit code cannot tell these apart."""
        world["result"] = {"ok": False, "attempted": False,
                           "error": "Could not connect", "stage": "connect"}
        assert check("Default", "r1")["verdict"] != REFUSED

    def test_an_unknown_device_is_inconclusive_not_refused(self, monkeypatch):
        monkeypatch.setattr("modules.device.load_saved_devices", lambda p: [])
        monkeypatch.setattr("modules.nsot.listref.resolve",
                            lambda name: type("R", (), {
                                "name": "Default", "csv_path": "/x"})())
        assert check("Default", "nope")["verdict"] == INCONCLUSIVE

    def test_no_stored_credential_is_inconclusive(self, world, monkeypatch):
        monkeypatch.setattr("modules.device.decrypt_field", lambda v: "")
        assert check("Default", "r1")["verdict"] == INCONCLUSIVE


class TestItAsksTheDeviceTheWayNmasDoes:
    def test_it_uses_the_rotation_verifier(self):
        """Which already separates a device verdict from a local fault, and
        was built for this exact mistake on the rotation path."""
        from tests.astcheck import calls_in
        from tests.nmas_check_credential import check as fn

        assert calls_in(fn, "verify_new_credential") == 1

    def test_it_does_not_shell_out_to_ssh(self):
        from tests.astcheck import code_of
        from tests.nmas_check_credential import check as fn

        source = code_of(fn)
        for shell in ("subprocess", "sshpass", "os.system", "popen"):
            assert shell not in source, shell


class TestTheSuppliedPasswordPathIsDistinct:
    def test_a_supplied_password_is_used_verbatim(self, world, monkeypatch):
        """`--password admin` must not be Fernet-decrypted. That exact
        confusion produced the r2 defect."""
        seen = {}
        monkeypatch.setattr(
            "modules.nsot.credential_rotation.verify_new_credential",
            lambda row, user, pw, secret=None: seen.update(pw=pw) or {"ok": True})
        check("Default", "r1", password="admin")
        assert seen["pw"] == "admin"

    def test_the_stored_password_is_decrypted(self, world, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            "modules.nsot.credential_rotation.verify_new_credential",
            lambda row, user, pw, secret=None: seen.update(pw=pw) or {"ok": True})
        check("Default", "r1")
        assert seen["pw"] == "stored-pw"


class TestAPostLoginFailureIsNotARefusal:
    """`stage: after_login` means authentication SUCCEEDED.

    `verify_new_credential()` returns `attempted=True, ok=False,
    stage="after_login"` when the login worked and `enable()` or the
    `show running-config` read did not. Mapping that to REFUSED says the
    device rejected a credential it actually accepted.

    On the checklist's second loop -- `--password admin --expect refused` --
    it would have reported REFUSED and **passed**, while `admin` logged in
    perfectly well. That is the key-exchange false pass again, in a different
    place: a verdict about the credential decided by something that is not
    about the credential.
    """

    def test_it_reads_as_accepted(self, world):
        world["result"] = {"ok": False, "attempted": True,
                           "error": "ValueError: Failed to enter enable mode",
                           "stage": "after_login"}
        assert check("Default", "r1")["verdict"] == ACCEPTED

    def test_it_carries_a_warning(self, world):
        world["result"] = {"ok": False, "attempted": True,
                           "error": "ValueError: Failed to enter enable mode",
                           "stage": "after_login"}
        out = check("Default", "r1")
        assert "post-login step failed" in out["warning"]
        assert "credential is good" in out["warning"]

    def test_reading_nothing_back_is_the_same_case(self, world):
        world["result"] = {"ok": False, "attempted": True,
                           "error": "logged in but read nothing back",
                           "stage": "after_login"}
        assert check("Default", "r1")["verdict"] == ACCEPTED

    def test_a_refusal_at_LOGIN_is_still_a_refusal(self, world):
        """The distinction is the stage, not the `attempted` flag alone."""
        world["result"] = {"ok": False, "attempted": True,
                           "error": "Authentication failed", "stage": "connect"}
        assert check("Default", "r1")["verdict"] == REFUSED


class TestAcceptedSaysNothingAboutFailure:
    """A success carrying a failure word is the output people learn to skim,
    on a line that has to be read nine times after a redeploy."""

    def test_a_clean_accept_has_no_warning(self, world):
        out = check("Default", "r1")
        assert out["verdict"] == ACCEPTED
        assert "warning" not in out

    def test_a_clean_accept_says_what_succeeded(self, world):
        out = check("Default", "r1")
        assert "read the running config back" in out["reason"]

    def test_no_verdict_carries_a_stage_field(self, world):
        """`stage` was printed as "failed at:" for every verdict, including
        success, where it means how far it GOT."""
        for result in (
                {"ok": True, "attempted": True, "stage": "after_login"},
                {"ok": False, "attempted": True, "stage": "connect",
                 "error": "nope"},
                {"ok": False, "attempted": True, "stage": "after_login",
                 "error": "nope"}):
            world["result"] = result
            assert "stage" not in check("Default", "r1")

    def test_inconclusive_names_what_was_never_reached(self, world):
        world["result"] = {"ok": False, "attempted": False,
                           "error": "no matching key exchange method",
                           "stage": "connect"}
        out = check("Default", "r1")
        assert out["verdict"] == INCONCLUSIVE
        assert out["unreached"] == "connect"


class TestTheExitCodes:
    """`|| echo` in the checklist loops must catch everything but a clean
    pass, or a warning scrolls by unread."""

    def _run(self, monkeypatch, result, argv):
        import sys

        from tests.nmas_check_credential import _module as tool

        monkeypatch.setattr("modules.device.load_saved_devices", lambda p: [ROW])
        monkeypatch.setattr("modules.device.decrypt_field", lambda v: "pw")
        monkeypatch.setattr("modules.nsot.credential_rotation.enable_secret",
                            lambda row: "en")
        monkeypatch.setattr(
            "modules.nsot.credential_rotation.verify_new_credential",
            lambda *a, **k: result)
        monkeypatch.setattr("modules.nsot.listref.resolve",
                            lambda name: type("R", (), {
                                "name": "Default", "csv_path": "/x"})())
        monkeypatch.setattr("modules.config.get_current_list_name",
                            lambda: "Default")
        saved = sys.argv
        sys.argv = ["nmas-check-credential", *argv]
        try:
            return tool.main()
        finally:
            sys.argv = saved

    def test_clean_pass_is_zero(self, monkeypatch):
        assert self._run(monkeypatch,
                         {"ok": True, "attempted": True, "stage": "after_login"},
                         ["r1", "--expect", "accepted"]) == 0

    def test_wrong_verdict_is_one(self, monkeypatch):
        assert self._run(monkeypatch,
                         {"ok": False, "attempted": True, "stage": "connect",
                          "error": "no"},
                         ["r1", "--expect", "accepted"]) == 1

    def test_inconclusive_is_two(self, monkeypatch):
        assert self._run(monkeypatch,
                         {"ok": False, "attempted": False, "stage": "connect",
                          "error": "kex"},
                         ["r1", "--expect", "accepted"]) == 2

    def test_accepted_with_a_warning_is_three_not_zero(self, monkeypatch):
        """The expectation held and something else did not."""
        assert self._run(monkeypatch,
                         {"ok": False, "attempted": True,
                          "stage": "after_login", "error": "enable failed"},
                         ["r1", "--expect", "accepted"]) == 3

    def test_admin_logging_in_fails_the_refused_expectation(self, monkeypatch):
        """The dangerous case: a post-login failure on the OLD credential
        must not read as 'admin was refused'."""
        assert self._run(monkeypatch,
                         {"ok": False, "attempted": True,
                          "stage": "after_login", "error": "enable failed"},
                         ["r1", "--password", "admin", "--expect", "refused"]) == 1


class TestItNeverTracebacks:
    """A device-name typo at 2am must report, not crash.

    Two INCONCLUSIVE branches returned without `unreached`, and the printer
    indexed it directly -- so `nmas-check-credential s9` raised KeyError
    instead of saying s9 is not in the list. Found by running the four
    outputs rather than by reading them.
    """

    def _run(self, monkeypatch, argv, devices=None):
        import sys

        from tests.nmas_check_credential import _module as tool

        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda p: devices if devices is not None else [ROW])
        monkeypatch.setattr("modules.device.decrypt_field", lambda v: "pw")
        monkeypatch.setattr("modules.nsot.credential_rotation.enable_secret",
                            lambda row: "en")
        monkeypatch.setattr(
            "modules.nsot.credential_rotation.verify_new_credential",
            lambda *a, **k: {"ok": True, "attempted": True,
                             "stage": "after_login"})
        monkeypatch.setattr("modules.nsot.listref.resolve",
                            lambda name: type("R", (), {
                                "name": "Default", "csv_path": "/x"})())
        monkeypatch.setattr("modules.config.get_current_list_name",
                            lambda: "Default")
        saved = sys.argv
        sys.argv = ["nmas-check-credential", *argv]
        try:
            return tool.main()
        finally:
            sys.argv = saved

    def test_an_unknown_device_reports_rather_than_raises(self, monkeypatch):
        assert self._run(monkeypatch, ["s9", "--expect", "accepted"]) == 2

    def test_an_empty_inventory_reports_rather_than_raises(self, monkeypatch):
        assert self._run(monkeypatch, ["s1", "--expect", "accepted"],
                         devices=[]) == 2

    def test_every_inconclusive_branch_names_what_was_unreached(self):
        """The field the printer needs, set at every site that returns it."""
        import ast

        from tests.astcheck import tree_of
        from tests.nmas_check_credential import check as fn

        for node in ast.walk(tree_of(fn)):
            if not isinstance(node, ast.Return):
                continue
            dumped = ast.dump(node)
            if "INCONCLUSIVE" in dumped:
                assert "unreached" in dumped, ast.unparse(node)
