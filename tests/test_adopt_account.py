"""ADOPT step 1: the tool ADDS an account of its own and never touches the
supplied one (the operator's decision, 2026-09-29).

A fake router holds several accounts, so "the supplied account is untouched"
is asserted as the router's own state, line for line, after every outcome.
The staged copy of the new password is kept exactly when it is the only copy
(C106, C210).
"""

import os
import re

import pytest

from modules.nsot import adopt as A
from modules.nsot import credential_rotation as CR

SUPPLIED = "username admin privilege 15 password 0 admin"


class Router:
    def __init__(self, lines=(SUPPLIED,), refuse=()):
        self.lines = list(lines)
        self.passwords = {}
        self.refuse = refuse

    def apply(self, line):
        for needle in self.refuse:
            if needle in line:
                return "% Invalid input detected at '^' marker."
        m = re.match(r"username (\S+) privilege 15 algorithm-type scrypt secret (\S+)", line)
        if m:
            self.lines.append(f"username {m.group(1)} privilege 15 secret 9 $9$salt$hash")
            self.passwords[m.group(1)] = m.group(2)
        m = re.match(r"no username (\S+)$", line)
        if m:
            self.lines = [l for l in self.lines if not l.startswith(f"username {m.group(1)} ")]
            self.passwords.pop(m.group(1), None)
        return ""


class Session:
    def __init__(self, router):
        self.router, self.sent, self.disconnected = router, [], False

    def send_command(self, command, **kw):
        m = re.search(r"include \^username (\S+)", command)
        return "\n".join(l for l in self.router.lines if l.startswith(f"username {m.group(1)} "))

    def config_mode(self):
        return ""

    def exit_config_mode(self):
        return ""

    def send_command_timing(self, command, **kw):
        self.sent.append(command)
        return self.router.apply(command)

    def disconnect(self):
        self.disconnected = True


@pytest.fixture
def lab(tmp_path):
    router = Router()
    session = Session(router)
    recorded = []

    def verify(dev, user, pw):
        if router.passwords.get(user) == pw:
            return {"ok": True, "config": "\n".join(router.lines)}
        return {"ok": False, "error": "Authentication failed", "attempted": True}

    return {"router": router, "session": session, "recorded": recorded, "verify": verify,
            "repo": str(tmp_path / "config_repo"), "device": {"ip": "192.0.2.50",
                                                             "username": "admin",
                                                             "password": "enc"}}


def _run(lab, **kw):
    kw.setdefault("open_session", lambda dev: lab["session"])
    kw.setdefault("verify", lab["verify"])
    kw.setdefault("record", lambda ip, user, pw: lab["recorded"].append((ip, user, pw)))
    return A.add_tool_account("Default", "bp-adopt-a", lab["device"], repo=lab["repo"],
                              actor="op@example.com", **kw)


def _staged(lab):
    return CR.staged_plaintext(lab["repo"], "bp-adopt-a")


class TestItAddsAndNeverRotates:
    def test_one_setter_line_the_account_verified_and_recorded(self, lab):
        out = _run(lab)
        assert out["state"] == A.ADDED, out
        sent = [l for l in lab["session"].sent if l.strip()]
        assert len(sent) == 1 and sent[0].startswith("username nmas privilege 15 algorithm-type")
        assert not [l for l in sent if "admin" in l], "nothing was sent about the supplied account"
        assert SUPPLIED in lab["router"].lines, "the supplied account is untouched"
        (ip, user, pw), = lab["recorded"]
        assert (ip, user) == ("192.0.2.50", "nmas") and lab["router"].passwords["nmas"] == pw
        assert _staged(lab) is None, "cleared only after the record"
        assert "untouched and used by nothing" in out["steps"][-1]["detail"]

    def test_the_program_masks_the_password(self):
        assert A.masked_program("nmas") == ["username nmas privilege 15 algorithm-type scrypt "
                                            "secret <generated>"]


class TestRefusedBeforeAnythingIsSent:
    def test_the_tool_account_may_not_be_the_supplied_one(self, lab):
        opened = []
        out = _run(lab, tool_username="admin", open_session=lambda d: opened.append(d))
        assert out["state"] == A.NOT_STARTED and "REPLACING" in out["reason"]
        assert opened == [] and lab["router"].lines == [SUPPLIED]

    def test_an_existing_account_by_that_name_is_somebodys(self, lab):
        theirs = "username nmas privilege 1 secret 9 $9$theirs$x"
        lab["router"].lines.append(theirs)
        out = _run(lab)
        assert out["state"] == A.NOT_STARTED and "did not create" in out["reason"]
        assert lab["session"].sent == [] and theirs in lab["router"].lines

    def test_a_supplied_credential_that_does_not_log_in(self, lab):
        def refuse(dev):
            raise RuntimeError("Authentication failed")
        out = _run(lab, open_session=refuse)
        assert out["state"] == A.NOT_STARTED and "supplied credential" in out["reason"]
        assert lab["router"].lines == [SUPPLIED]

    def test_a_refused_push_changes_nothing_and_keeps_no_staged_copy(self, lab):
        lab["router"].refuse = ("algorithm-type",)
        out = _run(lab)
        assert out["state"] == A.NOT_STARTED and "refused the new account" in out["reason"]
        assert lab["router"].lines == [SUPPLIED] and _staged(lab) is None


class TestAFailedVerifyRemovesOnlyWhatItAdded:
    def test_removed_and_read_back_gone(self, lab):
        out = _run(lab, verify=lambda d, u, p: {"ok": False, "error": "Authentication failed",
                                                "attempted": True})
        assert out["state"] == A.REVERTED and "read back gone" in out["reason"]
        assert "no username nmas" in lab["session"].sent
        assert lab["router"].lines == [SUPPLIED], "the supplied account is untouched"
        assert lab["recorded"] == [] and _staged(lab) is None

    def test_a_non_type_9_store_is_removed_too(self, lab):
        out = _run(lab, verify=lambda d, u, p: {
            "ok": True, "config": "username nmas privilege 15 secret 5 $1$x$y"})
        assert out["state"] == A.REVERTED and "not a type-9 secret" in out["reason"]

    def test_a_removal_that_cannot_be_proven_keeps_the_staged_copy(self, lab):
        lab["router"].refuse = ("no username",)
        out = _run(lab, verify=lambda d, u, p: {"ok": False, "error": "x", "attempted": True})
        assert out["state"] == A.REVERT_FAILED and "could NOT be proven removed" in out["reason"]
        assert _staged(lab) is not None, "the staged copy is the only copy of that password"


class TestAFailedRecordKeepsTheOnlyCopy:
    def test_added_not_recorded(self, lab):
        def fail(ip, user, pw):
            raise OSError("credential store unreadable")
        out = _run(lab, record=fail)
        assert out["state"] == A.ADDED_NOT_RECORDED and "ONLY copy" in out["reason"]
        # Not the rotation recovery: it needs an inventory row an adopting
        # device does not have, so naming it would point at a tool that stops.
        assert "nmas-rotation-recover" not in out["reason"]
        assert out["staged_at"].endswith("bp-adopt-a.enc") and "still logs in" in out["reason"]
        assert _staged(lab) == lab["router"].passwords["nmas"]
        assert SUPPLIED in lab["router"].lines


class TestTheSessionIsAlwaysClosed:
    @pytest.mark.parametrize("verify_ok", [True, False])
    def test_disconnected(self, lab, verify_ok):
        verify = lab["verify"] if verify_ok else (lambda d, u, p: {"ok": False, "error": "x"})
        _run(lab, verify=verify)
        assert lab["session"].disconnected
