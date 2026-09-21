"""Presence is not applicability.

Stage B, measured on hardware 2026-09-21: five routers' startup files each
contained the type-9 hash the rotation had just written. `verify_startup_file()`
grepped for it, found it, and passed -- correctly, for the question it asked.
Not one of those files would have applied.

vrnetlab's launch script concatenates its own
`username admin privilege 15 password admin` ahead of the startup config, and
IOS-XE refuses a secret for a user that already has a password. The node boots,
reaches `Startup complete`, reports healthy, and answers SSH on the injected
credential. Nothing fails. The first symptom would have been NMAS unable to log
in to all five at once, after the state that explained it was gone.

`verify_startup_applies()` asks the other question. The tests below are the
ones that would have failed in stage 1, when the first router rotated.

**It reads the launch script rather than encoding a platform rule.** "A secret
line is unappliable on a C8000v" was true when it was written and false the
moment the stage-C user-skip was adopted. A rule would have had to be
remembered; reading the thing it depends on cannot go stale.
"""

import pytest

import modules.nsot.credential_rotation as cr
from modules.nsot.bootstrap_config import LAUNCH_SKIP_MARKER

STOCK_LAUNCH = "cfg = self.gen_bootstrap_config() + startup_cfg\n"
PATCHED_LAUNCH = (
    "cfg = %s(\n    self.gen_bootstrap_config(), startup_cfg) + startup_cfg\n"
    % LAUNCH_SKIP_MARKER)

SECRET_FILE = """hostname r1
!
username admin privilege 15 secret 9 $9$saltsalt$hashhash
!
end
"""
PASSWORD_FILE = """hostname r1
!
username admin privilege 15 password 0 bootstrapvalue
!
end
"""


@pytest.fixture
def reads(monkeypatch):
    """Serve file contents by remote path, recording what was asked for."""
    served = {}
    asked = []

    def _fake(clab, command, **kwargs):
        asked.append(command)
        for path, text in served.items():
            if path in command:
                return {"ok": True, "text": text}
        return {"ok": False, "error": "No such file or directory"}

    monkeypatch.setattr(cr, "_ssh_read", _fake)
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "clab_host": "user@lab",
                            "clab_configs_dir": "labs/lab/configs",
                            "clab_launch_patch": "labs/lab/patches/c8000v-launch.py",
                        }.get(key, default))
    return {"served": served, "asked": asked}


class TestTheStageBCase:
    """The exact configuration that was live on all five routers."""

    def test_a_secret_file_behind_a_stock_launch_script_is_refused(self, reads):
        reads["served"]["labs/lab/configs/r1.cfg"] = SECRET_FILE
        reads["served"]["c8000v-launch.py"] = STOCK_LAUNCH

        out = cr.verify_startup_applies("r1", platform="cisco_iosxe",
                                        username="admin")
        assert out["ok"] is False
        assert out["applies"] is False

    def test_the_refusal_says_what_would_happen(self, reads):
        """A refusal nobody can act on gets overridden."""
        reads["served"]["labs/lab/configs/r1.cfg"] = SECRET_FILE
        reads["served"]["c8000v-launch.py"] = STOCK_LAUNCH

        error = cr.verify_startup_applies("r1", platform="cisco_iosxe",
                                          username="admin")["error"]
        assert "WILL NOT APPLY" in error
        assert "locked out" in error
        assert "CVAC" in error, "name the log line the operator will see"

    def test_the_refusal_names_both_ways_out(self, reads):
        reads["served"]["labs/lab/configs/r1.cfg"] = SECRET_FILE
        reads["served"]["c8000v-launch.py"] = STOCK_LAUNCH

        error = cr.verify_startup_applies("r1", platform="cisco_iosxe",
                                          username="admin")["error"]
        assert "user-skip" in error            # fix (a)
        assert "password form" in error        # fix (b)

    def test_presence_would_have_passed_the_same_file(self):
        """The two checks disagree on this input. That is the whole point."""
        assert "$9$saltsalt$hashhash" in SECRET_FILE


class TestAdoptingThePatchSatisfiesIt:
    """Stage C's fix, and the reason the check reads rather than rules."""

    def test_a_secret_file_behind_a_patched_launch_script_applies(self, reads):
        reads["served"]["labs/lab/configs/r1.cfg"] = SECRET_FILE
        reads["served"]["c8000v-launch.py"] = PATCHED_LAUNCH

        out = cr.verify_startup_applies("r1", platform="cisco_iosxe",
                                        username="admin")
        assert out["ok"] is True
        assert out["applies"] is True
        assert LAUNCH_SKIP_MARKER in out["reason"]

    def test_removing_the_patch_breaks_it_again(self, reads):
        """A launch script replaced with a stock one must re-fail.

        This is what a hardcoded rule could not do: it would have been
        updated once, at adoption, and then been wrong forever after.
        """
        reads["served"]["labs/lab/configs/r1.cfg"] = SECRET_FILE
        reads["served"]["c8000v-launch.py"] = PATCHED_LAUNCH
        assert cr.verify_startup_applies("r1", platform="cisco_iosxe",
                                         username="admin")["ok"] is True

        reads["served"]["c8000v-launch.py"] = STOCK_LAUNCH
        assert cr.verify_startup_applies("r1", platform="cisco_iosxe",
                                         username="admin")["ok"] is False

    def test_the_marker_is_the_one_the_patcher_writes(self):
        """The check greps for a name another file defines.

        If they drift, this degrades to "always refuses" -- which reads like
        a safe failure and is actually a check that has stopped measuring
        anything.
        """
        with open("docs/bootstrap-probe/patches/patch-skip-injected-user.py",
                  encoding="utf-8") as handle:
            assert LAUNCH_SKIP_MARKER in handle.read()


class TestThePasswordFormApplies:
    def test_it_passes_behind_a_stock_script(self, reads):
        """Fix (b): the injected line lands first and is then overwritten by
        an identical-form line, which IOS accepts."""
        reads["served"]["labs/lab/configs/r1.cfg"] = PASSWORD_FILE
        reads["served"]["c8000v-launch.py"] = STOCK_LAUNCH

        out = cr.verify_startup_applies("r1", platform="cisco_iosxe",
                                        username="admin")
        assert out["ok"] is True
        assert out["kind"] == "password"

    def test_it_does_not_need_to_read_the_launch_script(self, reads):
        """It applies either way, so asking would be a dependency on
        something that cannot change the answer."""
        reads["served"]["labs/lab/configs/r1.cfg"] = PASSWORD_FILE
        cr.verify_startup_applies("r1", platform="cisco_iosxe", username="admin")
        assert not any("launch" in command for command in reads["asked"])


class TestPlatformsWhereNothingIsInjected:
    """The switches. Their `secret 9` line is the only one and applies."""

    def test_ios_short_circuits(self, reads):
        out = cr.verify_startup_applies("s1", platform="cisco_ios",
                                        username="admin")
        assert out["ok"] is True

    def test_it_reads_nothing_at_all(self, reads):
        cr.verify_startup_applies("s1", platform="cisco_ios", username="admin")
        assert reads["asked"] == []

    def test_it_does_not_need_a_lab_host(self, monkeypatch):
        """Requiring one would fail for a reason unrelated to the question,
        and a check that fails spuriously gets worked around."""
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: default)
        out = cr.verify_startup_applies("s1", platform="cisco_ios",
                                        username="admin")
        assert out["ok"] is True


class TestUnknownIsNotFine:
    """This check exists because something unverifiable was treated as
    verified. It must not do that itself."""

    def test_an_unreadable_startup_file_is_refused(self, reads):
        out = cr.verify_startup_applies("r1", platform="cisco_iosxe",
                                        username="admin")
        assert out["ok"] is False
        assert "could not read" in out["error"]

    def test_an_unreadable_launch_script_is_refused(self, reads):
        reads["served"]["labs/lab/configs/r1.cfg"] = SECRET_FILE
        out = cr.verify_startup_applies("r1", platform="cisco_iosxe",
                                        username="admin")
        assert out["ok"] is False
        assert "unknown, not fine" in out["error"]

    def test_a_missing_username_line_is_refused(self, reads):
        reads["served"]["labs/lab/configs/r1.cfg"] = "hostname r1\n!\nend\n"
        reads["served"]["c8000v-launch.py"] = STOCK_LAUNCH
        out = cr.verify_startup_applies("r1", platform="cisco_iosxe",
                                        username="admin")
        assert out["ok"] is False
        assert "no `username admin` line" in out["error"]

    def test_an_unreadable_form_is_treated_as_a_secret(self, reads):
        """`entry_kind` returns "" when it cannot tell, and the caller's rule
        is assume the worst."""
        reads["served"]["labs/lab/configs/r1.cfg"] = (
            "username admin privilege 15 somethingelse xyz\n")
        reads["served"]["c8000v-launch.py"] = STOCK_LAUNCH
        assert cr.verify_startup_applies("r1", platform="cisco_iosxe",
                                         username="admin")["ok"] is False


class TestItIsWiredIntoTheChain:
    def test_platform_has_no_default(self):
        """A required input with a default is not required -- the same
        correction as `operation_fingerprint` and `save_golden(allow_new)`."""
        import inspect

        parameter = inspect.signature(cr.persist).parameters["platform"]
        assert parameter.default is inspect.Parameter.empty

    def test_the_stage_runs_after_the_presence_check(self, monkeypatch):
        order = []
        for name in ("update_oxidized_row", "reload_oxidized", "confirm_fetch",
                     "run_sync"):
            monkeypatch.setattr(cr, name, lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "verify_startup_file",
                            lambda *a, **k: order.append("presence") or {"ok": True})
        monkeypatch.setattr(cr, "verify_startup_applies",
                            lambda *a, **k: order.append("applies") or {"ok": True})

        cr.persist({"device": "r1", "steps": []}, mgmt_ip="203.0.113.1",
                   username="admin", password="pw", hostname="r1",
                   new_hash="9 $9$s$h", after_iso=cr.utc_now(),
                   platform="cisco_iosxe")
        assert order == ["presence", "applies"]

    def test_a_file_that_will_not_apply_denies_persisted(self, monkeypatch):
        """The state must not claim redeploy survival the boot would refuse."""
        for name in ("update_oxidized_row", "reload_oxidized", "confirm_fetch",
                     "run_sync", "verify_startup_file"):
            monkeypatch.setattr(cr, name, lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "verify_startup_applies",
                            lambda *a, **k: {"ok": False, "error": "WILL NOT APPLY"})

        out = cr.persist({"device": "r1", "steps": []}, mgmt_ip="203.0.113.1",
                         username="admin", password="pw", hostname="r1",
                         new_hash="9 $9$s$h", after_iso=cr.utc_now(),
                         platform="cisco_iosxe")
        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert out["persistence"][-1]["name"] == "startup_applies"

    def test_the_success_wording_claims_applicability_not_presence(self,
                                                                   monkeypatch):
        for name in ("update_oxidized_row", "reload_oxidized", "confirm_fetch",
                     "run_sync", "verify_startup_file", "verify_startup_applies"):
            monkeypatch.setattr(cr, name, lambda *a, **k: {"ok": True})

        out = cr.persist({"device": "r1", "steps": []}, mgmt_ip="203.0.113.1",
                         username="admin", password="pw", hostname="r1",
                         new_hash="9 $9$s$h", after_iso=cr.utc_now(),
                         platform="cisco_iosxe")
        assert out["state"] == cr.ROTATED_PERSISTED
        assert "applies on boot" in out["reason"]


class TestItCarriesTheListRatherThanAskingWhichIsActive:
    def test_platform_of_takes_a_list_name(self):
        import inspect

        assert "list_name" in inspect.signature(cr.platform_of).parameters

    def test_it_does_not_read_the_active_list(self):
        import inspect

        source = inspect.getsource(cr.platform_of)
        assert "get_current_list_name" not in source
        assert "get_current_device_list" not in source
