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
