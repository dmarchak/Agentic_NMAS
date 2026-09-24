"""A deploy may ADD an account; it may never CHANGE one.

**The worst failure available on the deploy path is a lockout dressed as a
configuration change.** A type-9 secret carries a per-hash salt and cannot be
regenerated. If committed intent names a secret ref whose stored value is not
byte-identical to what the device holds, the render carries a *different*
credential — and every other guard passes it: it is not a mask, it is
printable ASCII, it is present in the intended config, and it is not a
dangerous command. The push succeeds, the device changes password, and the
tool keeps the old one.

Asked for before the branch-site deploy, which is the first configuration this
tool authors rather than extracts, and therefore the first time a hand-written
`secret_ref` reaches a device.
"""

import pytest

from modules.nsot import deploy
from modules.nsot.render_artifact import (CredentialWouldChange,
                                          credential_form, credential_lines)

HASH = "$9$aBcD3fGh1JkLmN0"
CAPTURE = f"""hostname r6
username admin privilege 15 secret 9 {HASH}
enable secret 9 $9$ZZtopZZtopZZtop
interface Loopback0
 ip address 10.255.1.16 255.255.255.255
end
"""


class _Artifact:
    """What `prepare_device()` reads. Duck-typed, like `RestoreTarget`."""

    def __init__(self, capture=CAPTURE, device="r6"):
        self.device = device
        self.capture_credentials = credential_lines(capture)


def _assert(rendered, artifact=None):
    deploy.assert_credentials_unchanged(rendered, artifact or _Artifact())


class TestOnlyAChangedCredentialRefuses:

    def test_the_same_line_passes(self):
        """**The floor.** A guard that refused everything would satisfy every
        refusal below and leave the deploy path with no acceptance at all."""
        _assert(CAPTURE)

    def test_one_character_of_the_hash_refuses(self):
        """The salt case, exactly: a hash that is *almost* the stored one."""
        with pytest.raises(CredentialWouldChange) as exc:
            _assert(CAPTURE.replace(HASH, HASH[:-1] + "X"))
        assert "username:admin" in str(exc.value)
        assert "lockout" in str(exc.value)

    def test_the_same_value_in_a_different_form_refuses(self):
        """`secret 9` becoming `secret 0` is the whole finding, and the two
        lines differ by one character that is not part of the value."""
        with pytest.raises(CredentialWouldChange):
            _assert(CAPTURE.replace("secret 9 ", "secret 0 "))

    def test_the_enable_secret_is_covered_too(self):
        with pytest.raises(CredentialWouldChange) as exc:
            _assert(CAPTURE.replace("$9$ZZtopZZtopZZtop", "$9$somethingElse"))
        assert "enable" in str(exc.value)

    def test_a_new_account_is_allowed(self):
        """Additive, and it cannot lock anyone out of an account they use.

        Refusing this would make the guard block a legitimate change, which is
        how a guard gets removed rather than fixed.
        """
        _assert(CAPTURE + "username reader privilege 1 secret 9 $9$newAccount\n")

    def test_an_absent_line_is_not_this_guard_s_business(self):
        """Merge-only never removes a line, so a render that omits one cannot
        take the credential off the device. Claiming otherwise would be a
        second answer to a question `classify_diff` already answers."""
        _assert("hostname r6\nend\n")

    def test_a_line_for_a_DIFFERENT_user_is_not_a_change_to_this_one(self):
        """Keyed on the account, not the position."""
        _assert(CAPTURE.replace("username admin", "username admin") +
                "username other privilege 1 secret 9 $9$other\n")


class TestTheRefusalNeverQuotesTheCredential:
    """A guard against a credential leaking a credential is the trail that
    copies the secret it records."""

    def test_neither_hash_appears_in_the_message(self):
        with pytest.raises(CredentialWouldChange) as exc:
            _assert(CAPTURE.replace(HASH, "$9$totallyDifferentHash"))
        message = str(exc.value)
        assert HASH not in message
        assert "totallyDifferentHash" not in message
        assert "secret 9 <value>" in message, \
            "the FORM must survive, or the operator learns nothing"

    def test_a_plaintext_password_is_not_echoed_either(self):
        artifact = _Artifact("username admin privilege 15 password 0 hunter2\n")
        with pytest.raises(CredentialWouldChange) as exc:
            _assert("username admin privilege 15 password 0 correcthorse\n",
                    artifact)
        assert "hunter2" not in str(exc.value)
        assert "correcthorse" not in str(exc.value)


class TestItRunsWhereItCannotBeSkipped:
    """An optional argument is how a caller bypasses a guard by omission —
    measured twice in this project already, most recently inside the device →
    lab map that exists to prevent exactly that."""

    def test_prepare_device_calls_it(self):
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(deploy.prepare_device))
        called = {n.func.id for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "assert_credentials_unchanged" in called, (
            "the guard exists and the deploy path does not call it")

    def test_it_runs_after_the_mask_check_and_before_any_return(self):
        """Order is load-bearing in both directions.

        AFTER `assert_no_mask`: the masked render differs from the capture by
        construction, so running it earlier would refuse every deploy.
        BEFORE the return: `prepare_device()`'s contract is that nothing may
        open a socket until it has returned.
        """
        import inspect

        src = inspect.getsource(deploy.prepare_device)
        mask = src.index("assert_no_mask")
        guard = src.index("assert_credentials_unchanged")
        ret = src.index("return {")
        assert mask < guard < ret

    def test_the_artifact_carries_the_capture_credentials(self):
        """Not a parameter. `build_artifact()` already receives the capture,
        so there is no construction path that can lack it."""
        from modules.nsot.render_artifact import build_artifact

        artifact = build_artifact("r6", CAPTURE, "cisco_iosxe")
        assert artifact.capture_credentials, \
            "the artifact did not pick up the capture's credential lines"
        assert "username:admin" in artifact.capture_credentials

    def test_a_masked_render_would_have_refused_everything(self):
        """Pins WHY the order is what it is, rather than leaving it to a
        comment somebody may reorder for efficiency."""
        from modules.nsot.render_artifact import MASK

        with pytest.raises(CredentialWouldChange):
            _assert(CAPTURE.replace(HASH, MASK))


class TestCredentialFormDropsTheValue:

    def test_a_type_9_secret_keeps_its_type_and_loses_its_hash(self):
        out = credential_form(f"username admin privilege 15 secret 9 {HASH}")
        assert out == "username admin privilege 15 secret 9 <value>"

    def test_a_type_0_password_keeps_its_type(self):
        assert credential_form("username admin password 0 hunter2") == \
            "username admin password 0 <value>"

    def test_an_unparseable_line_still_says_something_and_leaks_nothing(self):
        out = credential_form("username admin")
        assert "admin" in out and "…" in out


class TestTheScanFindsSomething:
    """`credential_lines` returning `{}` would make every assertion above
    vacuous — the guard would pass by finding no credentials to compare."""

    def test_the_fleet_fixtures_really_do_carry_credential_lines(self):
        import os

        fleet = os.path.join(os.path.dirname(__file__), "fixtures", "configs",
                             "fleet")
        total = 0
        for name in sorted(os.listdir(fleet)):
            with open(os.path.join(fleet, name), encoding="utf-8") as fh:
                total += len(credential_lines(fh.read()))
        assert total >= 9, (
            f"only {total} credential line(s) found across the fleet — the "
            "matcher is finding nothing, which is indistinguishable from a "
            "fleet with no credentials")

    def test_an_indented_line_is_not_a_top_level_credential(self):
        """`line vty 0` blocks carry an indented `password`, which belongs to
        the line and not to an account."""
        assert credential_lines("line vty 0 4\n password 0 vtypass\n") == {}
