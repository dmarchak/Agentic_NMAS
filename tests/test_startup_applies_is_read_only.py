"""Reaching a read-only check required a live rotation.

`verify_startup_applies()` is two `cat`s over SSH — the device's startup
config and the launch script it binds. It opens no session to the device and
changes nothing.

Its only caller was a **stage of the persistence chain**, so the Stage 2
runbook told the operator to run `nmas-rotate-credential` on s1 and r1 to
watch it pass. That performs a real rotation: a new random password on a live
device, minutes before a redeploy whose post-items verify exactly those
credentials, invalidating the baseline and the credential snapshot taken in
the pre-items moments earlier.

And the negative control was worse. `nmas-persist-credential --dry-run`
*looks* like the read-only form; it returns after the preconditions and
**never enters the chain**, so it never runs this stage at all. It prints the
same line whether the launch script carries the user-skip or not — a control
that cannot fail, guarding the check whose whole purpose is to fail when the
skip is absent.

Nothing about the check required a rotation. It simply had no caller of its
own.
"""

import pytest

from tests.nmas_check_startup_applies import check_one

ROW = {"hostname": "r1", "ip": "203.0.113.1", "username": "admin",
       "device_type": "cisco_xe"}


@pytest.fixture
def world(monkeypatch):
    calls = {"verify": [], "rotate": 0, "connect": 0}

    monkeypatch.setattr("modules.device.load_saved_devices", lambda p: [ROW])
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: type("R", (), {
                            "name": "Default", "csv_path": "/x"})())
    monkeypatch.setattr("modules.nsot.credential_rotation.platform_of",
                        lambda lst, host: "cisco_iosxe")

    def _verify(hostname, *, platform, username, **kw):
        calls["verify"].append((hostname, platform, username))
        return {"ok": True, "applies": True, "reason": "the skip is present"}

    monkeypatch.setattr(
        "modules.nsot.credential_rotation.verify_startup_applies", _verify)
    # Tripwires: if the check ever rotates or connects, these fire.
    monkeypatch.setattr("modules.nsot.credential_rotation.rotation_commands",
                        lambda *a, **k: calls.__setitem__("rotate",
                                                          calls["rotate"] + 1))
    monkeypatch.setattr("modules.nsot.credential_rotation.verify_new_credential",
                        lambda *a, **k: calls.__setitem__("connect",
                                                          calls["connect"] + 1))
    return calls


class TestItIsReadOnly:
    def test_it_asks_the_applicability_check(self, world):
        out = check_one("Default", "r1")
        assert out["ok"] is True
        assert world["verify"] == [("r1", "cisco_iosxe", "admin")]

    def test_it_rotates_nothing(self, world):
        check_one("Default", "r1")
        assert world["rotate"] == 0

    def test_it_opens_no_session_to_the_device(self, world):
        check_one("Default", "r1")
        assert world["connect"] == 0

    def test_it_never_calls_the_rotation_entry_points(self):
        """Structural as well: a future edit must not reach for them."""
        from tests.astcheck import calls_in
        from tests.nmas_check_startup_applies import check_one as fn

        for forbidden in ("rotate", "push_rotation", "verify_new_credential",
                          "persist", "save_golden"):
            assert calls_in(fn, forbidden) == 0, forbidden


class TestItRefusesRatherThanGuessing:
    def test_an_unknown_device(self, world):
        out = check_one("Default", "nope")
        assert out["ok"] is False
        assert "not in list" in out["error"]

    def test_a_device_with_no_platform(self, world, monkeypatch):
        """The check is platform-specific; guessing would make it answer a
        question about a platform the device may not be."""
        monkeypatch.setattr("modules.nsot.credential_rotation.platform_of",
                            lambda lst, host: "")
        out = check_one("Default", "r1")
        assert out["ok"] is False
        assert "cannot guess" in out["error"]


class TestItCarriesTheVerdictThrough:
    def test_a_refusal_is_reported(self, world, monkeypatch):
        monkeypatch.setattr(
            "modules.nsot.credential_rotation.verify_startup_applies",
            lambda h, **k: {"ok": False, "applies": False,
                            "error": "the hash is in r1.cfg and the file WILL "
                                     "NOT APPLY"})
        out = check_one("Default", "r1")
        assert out["ok"] is False
        assert "WILL NOT APPLY" in out["error"]

    def test_the_platform_is_reported(self, world):
        assert check_one("Default", "r1")["platform"] == "cisco_iosxe"


class TestTheDryRunItReplacesCouldNotHaveWorked:
    """Pinning why the old negative control was inert."""

    def test_persist_dry_run_returns_before_the_chain(self):
        import io
        import os

        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "scripts", "nmas-persist-credential")
        with io.open(path, encoding="utf-8") as handle:
            source = handle.read()

        dry = source.index("if args.dry_run:")
        chain = source.index("cr.persist(")
        assert dry < chain, (
            "if persist() ever runs before the dry-run guard, this script "
            "stops being read-only and the runbook must change")
        between = source[dry:chain]
        assert "return 0" in between, (
            "the dry run must return before the chain; otherwise it is not a "
            "dry run")
