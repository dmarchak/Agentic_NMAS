"""ADOPT step 1: the tool ADDS an account of its own and never touches the
supplied one (the operator's decisions, 2026-09-29).

A fake router holds several accounts, so "the supplied account is untouched"
is asserted as the router's own state, line for line, after every outcome.
The staged copy of the new password is kept exactly when it is the only copy
(C106, C210). The SUPPLIED credential is never written anywhere, on every
path, success and failure alike. A device whose logins would never consult a
local account is refused before anything is sent, naming why, judged against
the real fleet's configs.
"""

import glob
import json
import os
import re

import pytest

from modules.nsot import adopt as A
from modules.nsot import credential_rotation as CR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUPPLIED_PW = "Supplied-Owner-Pass-7391"      # long enough for value redaction
SUPPLIED = f"username admin privilege 15 password 0 {SUPPLIED_PW}"
LOCAL_VTY = "line vty 0 4\n login local\n transport input ssh\n"


class Router:
    def __init__(self, lines=(SUPPLIED,), refuse=(), aaa="", vty=LOCAL_VTY):
        self.lines = list(lines)
        self.passwords = {}
        self.refuse = refuse
        self.aaa, self.vty = aaa, vty

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
        if "include ^aaa" in command:
            return self.router.aaa
        if "section ^line vty" in command:
            return self.router.vty
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
            "repo": str(tmp_path / "config_repo")}


def _run(lab, **kw):
    kw.setdefault("open_session", lambda dev: lab["session"])
    kw.setdefault("verify", lab["verify"])
    kw.setdefault("record", lambda ip, user, pw: lab["recorded"].append((ip, user, pw)))
    kw.setdefault("supplied_username", "admin")
    kw.setdefault("supplied_password", SUPPLIED_PW)
    return A.add_tool_account("Default", "bp-adopt-a", mgmt_ip="192.0.2.50",
                              device_type="cisco_xe", repo=lab["repo"],
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

    def test_a_device_whose_logins_skip_local_accounts_says_why(self, lab):
        lab["router"].aaa = ("aaa new-model\naaa authentication login default group tacacs+ "
                             "local\n")
        out = _run(lab)
        assert out["state"] == A.NOT_STARTED
        assert "only if the servers do not answer" in out["reason"]
        assert "'default' = group tacacs+ local" in out["reason"]
        assert lab["session"].sent == [] and lab["router"].lines == [SUPPLIED]


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


class TestTheSuppliedCredentialIsNeverWritten:
    """No file written during an adoption holds the supplied value, raw or as
    a Fernet token that decrypts to it; nor does any log record or the result.
    Every outcome, the failure paths included, and a library error that
    QUOTES the password (the shape a careless exception message takes)."""

    def _files_hold_it(self, roots):
        from modules.device import fernet
        hits = []
        # os.walk, never glob("**"): glob skips hidden directories, and the
        # staging area is `.nsot/staging/` (found by this test's own control,
        # which staged the supplied password there and passed).
        paths = [os.path.join(d, f) for root in roots for d, _, fs in os.walk(root) for f in fs]
        assert paths, "a scan that read no file proves nothing"
        for path in paths:
            if True:
                data = open(path, "rb").read()
                if SUPPLIED_PW.encode() in data:
                    hits.append((path, "raw"))
                for token in re.findall(rb"gAAAAA[A-Za-z0-9_\-=]+", data):
                    try:
                        if fernet.decrypt(token).decode() == SUPPLIED_PW:
                            hits.append((path, "encrypted"))
                    except Exception:            # noqa: BLE001
                        pass
        return hits

    @pytest.mark.parametrize("case", ["added", "login_refused", "local_skipped", "exists",
                                      "push_refused", "verify_failed", "removal_unproven",
                                      "record_failed", "echoing_error"])
    def test_on_every_path(self, lab, case, caplog):
        from modules import config
        # The REAL record on the success path, so the credential store is
        # actually written in this test's store and the scan reads it.
        kw = {"record": None} if case == "added" else {}
        if case == "login_refused":
            kw["open_session"] = lambda d: (_ for _ in ()).throw(RuntimeError("refused"))
        elif case == "echoing_error":
            kw["open_session"] = lambda d: (_ for _ in ()).throw(
                RuntimeError(f"bad password {SUPPLIED_PW} for admin"))
        elif case == "local_skipped":
            lab["router"].vty = "line vty 0 4\n login\n transport input ssh\n"
        elif case == "exists":
            lab["router"].lines.append("username nmas privilege 1 secret 9 $9$x$y")
        elif case == "push_refused":
            lab["router"].refuse = ("algorithm-type",)
        elif case in ("verify_failed", "removal_unproven"):
            kw["verify"] = lambda d, u, p: {"ok": False, "error": "x", "attempted": True}
            if case == "removal_unproven":
                lab["router"].refuse = ("no username",)
        elif case == "record_failed":
            kw["record"] = lambda ip, u, p: (_ for _ in ()).throw(OSError("store"))
        with caplog.at_level("DEBUG"):
            out = _run(lab, **kw)
        assert SUPPLIED_PW not in json.dumps(out), out
        assert SUPPLIED_PW not in caplog.text
        assert self._files_hold_it([config.DATA_DIR, lab["repo"]]) == []
        if case == "added":
            from modules import credentials
            assert credentials.has_device_override("192.0.2.50") and \
                credentials.resolve("192.0.2.50")["username"] == "nmas", \
                "the store WAS written (the tool's account), so the scan read a real write"

    def test_the_control_a_written_copy_is_seen(self, lab):
        """The scan can fail: a copy put where adoption must not write is found."""
        from modules import config
        from modules.device import fernet
        path = os.path.join(config.DATA_DIR, "planted_supplied.txt")
        with open(path, "w") as fh:
            fh.write(fernet.encrypt(SUPPLIED_PW.encode()).decode())
        try:
            assert self._files_hold_it([config.DATA_DIR]) == [(path, "encrypted")]
        finally:
            os.remove(path)


def _reads(config_text):
    """What the two device reads return, from a real config."""
    aaa = "\n".join(l for l in config_text.splitlines() if l.startswith("aaa"))
    vty, keep = [], False
    for line in config_text.splitlines():
        if line.startswith("line vty"):
            keep = True
        elif not line.startswith(" "):
            keep = False
        if keep:
            vty.append(line)
    return aaa, "\n".join(vty)


class TestTheVerdictOnRealConfigs:
    FLEET = sorted(glob.glob(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "*.cfg"))
                   + glob.glob(os.path.join(ROOT, "tests", "fixtures", "configs", "*.cfg")))

    def test_every_fleet_device_logs_in_locally(self):
        assert len(self.FLEET) >= 9
        for path in self.FLEET:
            verdict = A.local_login_verdict(*_reads(open(path).read()))
            assert verdict["ok"], (path, verdict)

    def _r1(self):
        return open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r1.cfg")).read()

    def test_the_line_password_is_refused_naming_the_line(self):
        aaa, vty = _reads(self._r1().replace(" login local", " login", 1))
        v = A.local_login_verdict(aaa, vty)
        assert not v["ok"] and "line vty 0 uses `login`" in v["reason"]
        assert "it would take `login local` on that line" in v["reason"]

    @pytest.mark.parametrize("aaa,words", [
        ("aaa new-model\naaa authentication login default group tacacs+ local",
         "only if the servers do not answer"),
        ("aaa new-model\naaa authentication login default group radius",
         "never consults a local account"),
        ("aaa new-model\naaa authentication login default local\n"
         "aaa authorization exec default group tacacs+",
         "would not grant a local account a shell"),
    ])
    def test_aaa_lists_that_skip_local_are_refused_saying_why(self, aaa, words):
        _, vty = _reads(self._r1())
        v = A.local_login_verdict(aaa, vty)
        assert not v["ok"] and words in v["reason"] and "nothing was sent" in v["reason"]

    def test_a_named_list_on_the_vty_is_the_one_judged(self):
        _, vty = _reads(self._r1())
        vty = vty.replace(" login local", " login authentication OPS")
        aaa = ("aaa new-model\naaa authentication login default group tacacs+\n"
               "aaa authentication login OPS local")
        assert A.local_login_verdict(aaa, vty)["ok"]
        assert "'MISSING', which is not defined" in A.local_login_verdict(
            aaa, vty.replace("OPS", "MISSING"))["reason"]

    def test_aaa_with_local_first_and_no_login_list_pass(self):
        _, vty = _reads(self._r1())
        assert A.local_login_verdict("aaa new-model\naaa authentication login default local",
                                     vty)["ok"]
        assert A.local_login_verdict("aaa new-model", vty)["ok"], "no list: the local database"

    def test_no_ssh_line_is_no_way_in(self):
        v = A.local_login_verdict("", "line vty 0 4\n login local\n transport input telnet\n")
        assert not v["ok"] and "no vty line accepts SSH" in v["reason"]


class TestTheTransientRedaction:
    def test_redacted_inside_the_block_and_forgotten_after(self):
        from modules import redact
        line = f"login failed for admin with {SUPPLIED_PW}"
        assert SUPPLIED_PW in redact.redact_text(line), "not a stored value, so not redacted"
        with redact.transient_secret(SUPPLIED_PW, "adopt:supplied"):
            assert SUPPLIED_PW not in redact.redact_text(line)
        assert SUPPLIED_PW in redact.redact_text(line), "held for the operation only"

    def test_a_short_value_is_not_added(self):
        from modules import redact
        with redact.transient_secret("admin", "adopt:supplied"):
            assert "admin" in redact.redact_text("username admin")
