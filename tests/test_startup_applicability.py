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


# ---------------------------------------------------------------------------
# The negative control, as a test
# ---------------------------------------------------------------------------

PATCHED_LAUNCH_FILE = '''#!/usr/bin/env python3
import datetime, logging, os, re, signal, sys, telnetlib
import vrnetlab


def _skip_users_defined_in_startup(bootstrap, startup):
    defined = set(re.findall(r"(?m)^\\s*username\\s+(\\S+)\\s", startup or ""))
    if not defined:
        return bootstrap
    return bootstrap


class C8000v_vm(vrnetlab.VM):
    def bootstrap_spin(self):
        startup_cfg = self.read_startup_config()
        cfg = _skip_users_defined_in_startup(
            self.gen_bootstrap_config(), startup_cfg) + startup_cfg
        self.write_config(cfg)
'''

STOCK_LAUNCH_FILE = '''#!/usr/bin/env python3
import datetime, logging, os, re, signal, sys, telnetlib
import vrnetlab


class C8000v_vm(vrnetlab.VM):
    def bootstrap_spin(self):
        startup_cfg = self.read_startup_config()
        cfg = self.gen_bootstrap_config() + startup_cfg
        self.write_config(cfg)
'''


@pytest.fixture
def launch_file(tmp_path, monkeypatch):
    """A REAL file on disk, read through the same code path.

    `_ssh_read` is redirected to `cat` the local file rather than stubbed
    with a string, so the check exercises its own parsing of real content --
    and so the negative control edits a file the way an operator does.
    """
    startup = tmp_path / "r1.cfg"
    startup.write_text("hostname r1\n!\n"
                       "username admin privilege 15 secret 9 $9$salt$hash\n!\nend\n",
                       encoding="utf-8")
    launch = tmp_path / "c8000v-launch.py"
    launch.write_text(PATCHED_LAUNCH_FILE, encoding="utf-8")

    def _fake_ssh_read(clab, command, **kwargs):
        # Behaves like `cat`: a missing file is a non-zero exit, not an
        # exception. Raising here would make the missing-file tests fail for
        # the fixture's reason rather than the code's.
        for path in (startup, launch):
            if str(path) in command:
                if not path.exists():
                    return {"ok": False,
                            "error": f"cat: {path}: No such file or directory"}
                return {"ok": True, "text": path.read_text(encoding="utf-8")}
        return {"ok": False, "error": "No such file or directory"}

    monkeypatch.setattr(cr, "_ssh_read", _fake_ssh_read)
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "clab_host": "user@lab",
                            "clab_configs_dir": str(tmp_path),
                            "clab_launch_patch": str(launch)}.get(key, default))
    return {"launch": launch, "startup": startup}


def _verdict(launch_file):
    return cr.verify_startup_applies("r1", platform="cisco_iosxe",
                                     username="admin")


class TestTheNegativeControl:
    """It failed on the live host, and that is why it is a test now.

    With the marker renamed to `_skip_users_defined_in_startupX`, the routers
    still reported APPLIES with the same reason text. The check did
    `LAUNCH_SKIP_MARKER in text` -- and the renamed identifier CONTAINS the
    marker. The control could not fail, and nine APPLIES lines were about to
    go into a redeploy as evidence.
    """

    def test_the_patched_file_applies(self, launch_file):
        assert _verdict(launch_file)["ok"] is True

    def test_renaming_the_helper_makes_it_refuse(self, launch_file):
        """The exact edit the runbook prescribes -- `sed s/X/XY/`."""
        text = launch_file["launch"].read_text(encoding="utf-8")
        launch_file["launch"].write_text(
            text.replace("_skip_users_defined_in_startup",
                         "_skip_users_defined_in_startupX"),
            encoding="utf-8")
        out = _verdict(launch_file)
        assert out["ok"] is False, (
            "the renamed identifier still contains the marker; a substring "
            "test cannot tell them apart")

    def test_a_stock_launch_script_refuses(self, launch_file):
        launch_file["launch"].write_text(STOCK_LAUNCH_FILE, encoding="utf-8")
        assert _verdict(launch_file)["ok"] is False

    def test_the_helper_defined_but_never_called_refuses(self, launch_file):
        """Half-undone: the function is there, the call site is not."""
        launch_file["launch"].write_text(
            PATCHED_LAUNCH_FILE.replace(
                "        cfg = _skip_users_defined_in_startup(\n"
                "            self.gen_bootstrap_config(), startup_cfg) + startup_cfg",
                "        cfg = self.gen_bootstrap_config() + startup_cfg"),
            encoding="utf-8")
        out = _verdict(launch_file)
        assert out["ok"] is False

    def test_a_mere_comment_mentioning_it_refuses(self, launch_file):
        launch_file["launch"].write_text(
            STOCK_LAUNCH_FILE + "\n# TODO: _skip_users_defined_in_startup\n",
            encoding="utf-8")
        assert _verdict(launch_file)["ok"] is False

    def test_a_half_patched_file_refuses_and_says_so(self, launch_file):
        """Both forms present: which one runs decides whether the device
        boots, and that is not something to guess."""
        launch_file["launch"].write_text(
            PATCHED_LAUNCH_FILE
            + "\n    def other(self):\n"
              "        cfg = self.gen_bootstrap_config() + startup_cfg\n",
            encoding="utf-8")
        out = _verdict(launch_file)
        assert out["ok"] is False
        assert "Half-patched" in out["error"]

    def test_restoring_the_marker_makes_it_apply_again(self, launch_file):
        launch_file["launch"].write_text(STOCK_LAUNCH_FILE, encoding="utf-8")
        assert _verdict(launch_file)["ok"] is False
        launch_file["launch"].write_text(PATCHED_LAUNCH_FILE, encoding="utf-8")
        assert _verdict(launch_file)["ok"] is True


class TestItNamesWhatItRead:
    """A verdict about a remote file that does not say which file, on which
    host, at what content, is a verdict nobody can check -- and it is read in
    a session where the operator has just edited that file."""

    def test_the_pass_names_host_path_and_digest(self, launch_file):
        out = _verdict(launch_file)
        assert "user@lab:" in out["launch_patch"]
        assert str(launch_file["launch"]) in out["launch_patch"]
        assert "@" in out["launch_patch"].rsplit("@", 1)[-1] or \
            len(out["launch_patch"].rsplit("@", 1)[-1]) == 12

    def test_the_digest_changes_with_the_file(self, launch_file):
        first = _verdict(launch_file)["launch_patch"]
        launch_file["launch"].write_text(
            PATCHED_LAUNCH_FILE + "\n# a change\n", encoding="utf-8")
        assert _verdict(launch_file)["launch_patch"] != first

    def test_the_refusal_names_it_too(self, launch_file):
        launch_file["launch"].write_text(STOCK_LAUNCH_FILE, encoding="utf-8")
        assert str(launch_file["launch"]) in _verdict(launch_file)["error"]


class TestAMissingLaunchScriptIsNeverAPass:
    def test_it_refuses(self, launch_file):
        launch_file["launch"].unlink()
        out = _verdict(launch_file)
        assert out["ok"] is False

    def test_it_is_marked_unknown_not_will_not_apply(self, launch_file):
        """"We could not look" and "we looked and it will not apply" are
        different facts."""
        launch_file["launch"].unlink()
        out = _verdict(launch_file)
        assert out.get("unknown") is True
        assert out.get("applies") is not False or "unknown" in out["error"]
