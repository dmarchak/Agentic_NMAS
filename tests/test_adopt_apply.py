"""ADOPT step 2: the preview and the apply, on r2's REAL configuration.

The device is r2's real config with ONE minimal edit: its `admin` account's
line is a type-9 secret (vrnetlab ships `password 0 admin`, which the golden
would record in clear; that case is refused, and is tested as such). A fake
router answers the reads, takes the one setter line and saves; the store, the
repository, the manifest, the inventory and the NetBox records are the real
ones, in the suite's temporary store.

What is asserted is the operator's decisions (2026-09-29): the tool ADDS an
account and never touches the supplied one; nothing else changes; persist is
previewed as running against startup; NetBox objects that existed are recorded
as ADOPTED, never as created; the result's next action is the break-glass
export; the supplied credential is never written; and a stopped adoption
RESUMES rather than adding a second account.
"""

import json
import logging
import os
import re
import subprocess

import pytest

from modules.nsot import adopt as A
from modules.nsot import credential_rotation as CR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R2 = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r2.cfg")
LIST, HOST, IP = "Lab", "r2", "192.0.2.50"
SUPPLIED_PW = "Supplied-Owner-Pass-7391"
REAL_ADMIN = "username admin privilege 15 password 0 admin"
HASHED_ADMIN = "username admin privilege 15 secret 9 $9$ownersalt$ownerhashvalue"
CLEAR_ADMIN = f"username admin privilege 15 password 0 {SUPPLIED_PW}"
EXISTING = [("dcim/devices", 7, "r2"), ("dcim/interfaces", 90, "GigabitEthernet1"),
            ("ipam/ip-addresses", 50, "192.0.2.50/24")]


def _config(admin=HASHED_ADMIN):
    text = open(R2, encoding="utf-8").read()
    assert REAL_ADMIN in text, "the fixture's own admin line moved"
    return text.replace(REAL_ADMIN, admin)


def _section(text, head):
    out, keep = [], False
    for line in text.splitlines():
        if line.startswith(head):
            keep = True
        elif not line.startswith(" "):
            keep = False
        if keep:
            out.append(line)
    return "\n".join(out)


class Router:
    """Answers as IOS-XE 17.06 does where it matters here (measured, rotation's
    record): a secret over a PASSWORD entry is refused, so only the
    delete-then-set program converts one. *store_as* makes the device store a
    different password for an account (a conversion whose fresh login then
    fails); *refuse* makes it refuse any line containing one of its words."""

    def __init__(self, running):
        self.load(running)
        self.passwords = {"admin": SUPPLIED_PW}
        self.sent, self.saves, self.store_as, self.refuse = [], 0, {}, ()

    def load(self, running):
        self.running = running.splitlines()
        self.startup = list(self.running)

    def text(self):
        return "\n".join(self.running)

    def _at(self):
        return next((i for i, l in enumerate(self.running) if l.startswith("username ")),
                    len(self.running))

    def apply(self, line):
        self.sent.append(line)
        if any(word in line for word in self.refuse):
            return "% Invalid input detected at '^' marker."
        m = re.match(r"no username (\S+)$", line)
        if m:
            self.running = [l for l in self.running if not l.startswith(f"username {m.group(1)} ")]
            self.passwords.pop(m.group(1), None)
            return ""
        m = re.match(r"username (\S+) privilege (\d+) algorithm-type scrypt secret (\S+)", line)
        if m:
            user = m.group(1)
            if any(l.startswith(f"username {user} ") and " password " in l
                   for l in self.running):
                return "ERROR: Can not have both a user password and a user secret."
            self.running = [l for l in self.running if not l.startswith(f"username {user} ")]
            self.running.insert(self._at(), f"username {user} privilege {m.group(2)} "
                                            f"secret 9 $9$s{len(self.sent)}$h")
            self.passwords[user] = self.store_as.get(user, m.group(3))
            return ""
        m = re.match(r"username (\S+) .*\bpassword 0 (\S+)$", line)
        if m:                                   # an original line put back
            self.running.insert(self._at(), line)
            self.passwords[m.group(1)] = m.group(2)
        return ""

    def reads(self, device, tool):
        if device.get("username") != "admin":
            raise RuntimeError("Authentication failed")
        text = self.text()
        return {"running": text, "startup": "\n".join(self.startup),
                "aaa": "\n".join(l for l in self.running if l.startswith("aaa")),
                "vty": _section(text, "line vty")}


class Session:
    def __init__(self, router):
        self.router, self.disconnected = router, False

    def send_command(self, command, **kw):
        text = self.router.text()
        if "include ^aaa" in command:
            return "\n".join(l for l in self.router.running if l.startswith("aaa"))
        if "section ^line vty" in command:
            return _section(text, "line vty")
        m = re.search(r"include \^username (\S+)", command)
        return "\n".join(l for l in self.router.running if l.startswith(f"username {m.group(1)} "))

    def config_mode(self):
        return ""

    def exit_config_mode(self):
        return ""

    def send_command_timing(self, command, **kw):
        return self.router.apply(command)

    def disconnect(self):
        self.disconnected = True


@pytest.fixture
def lab(monkeypatch, tmp_path):
    from modules import netbox_guard

    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    # Bound at import there (promotion asks it whether the list is NetBox-sourced).
    monkeypatch.setattr("modules.inventory.source_config.get_list_data_dir",
                        lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.listref._registry", lambda: {LIST: "lab"})
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    router = Router(_config())
    calls = {"netbox": 0, "existing": 0, "capture": [], "existing_for": []}
    _forget_records()

    def verify(dev, user, pw):
        if router.passwords.get(user) == pw:
            return {"ok": True, "config": router.text()}
        return {"ok": False, "error": "Authentication failed", "attempted": True}

    def persist(ip, user, pw, sec, dt):
        router.startup, router.saves = list(router.running), router.saves + 1
        return {"ok": True, "state": "persisted", "detail": "the startup config carries it"}

    def existing(hostname):
        calls["existing"] += 1
        calls["existing_for"].append(hostname)      # which device's objects were asked for
        return {"ok": True, "objects": list(EXISTING), "error": ""}

    def netbox(repo, hostname, list_name, *, actor, authority):
        calls["netbox"] += 1
        calls["authority"] = authority
        calls["netbox_args"] = (repo, hostname, list_name, actor)
        return {"ok": True, "created": [], "device_id": 7, "reason": ""}

    def capture(ip, user, pw, secret, device_type):
        # What it was asked with is kept, so a test can say whose login read the device.
        calls["capture"].append((ip, user, pw, secret, device_type))
        return {"ok": True, "config": router.text()}

    collab = {"read": router.reads, "open_session": lambda dev: Session(router),
              "verify": verify, "persist": persist, "capture": capture,
              "netbox_existing": existing, "netbox": netbox,
              "netbox_preview": lambda *a, **k: {"ok": True, "create_count": 12,
                                            "update_count": 3, "creates_by_type": {},
                                            "updates_by_type": {}}}
    yield {"router": router, "collab": collab, "calls": calls}
    _forget_records()


def _forget_records():
    """The suite shares one store for the session: what one adoption recorded
    (the tool's credential for IP, the NetBox records) must not reach the next."""
    from modules import credentials, netbox_guard
    if credentials.has_device_override(IP):
        credentials.clear_device_override(IP)
    for path in (netbox_guard._ADOPTED_FILE, netbox_guard._CREATED_IDS_FILE):
        if os.path.exists(path):
            os.remove(path)


def _plan(lab, **kw):
    args = {k: lab["collab"][k] for k in ("read", "netbox_existing", "netbox_preview")}
    args.setdefault("role", "router")       # asked since C225; r2 is a router
    args.update(kw)
    return A.plan(LIST, HOST, mgmt_ip=IP, platform="cisco_iosxe", supplied_username="admin",
                  supplied_password=SUPPLIED_PW, **args)


def _apply(lab, fingerprint=None, **kw):
    collab = dict(lab["collab"], **kw)
    collab.setdefault("role", "router")
    fingerprint = fingerprint if fingerprint is not None else _plan(lab)["fingerprint"]
    return A.apply(LIST, HOST, mgmt_ip=IP, platform="cisco_iosxe", supplied_username="admin",
                   supplied_password=SUPPLIED_PW, confirmed_fingerprint=fingerprint,
                   actor="op@example.com", reason="taking r2 into management", **collab)


def _repo():
    from modules.nsot.listref import resolve
    return resolve(LIST).repo_dir


def _git(*args):
    return subprocess.run(["git", "-C", _repo(), *args], capture_output=True,
                          text=True).stdout.strip()


class TestThePreview:
    def test_a_clean_preview_reads_only_and_says_everything(self, lab):
        out = _plan(lab)
        assert out["blocking"] == [], out["gates"]
        assert out["fingerprint"]
        assert out["program"] == A.masked_program("nmas")
        assert lab["router"].sent == [], "a preview sends nothing"
        assert CR.staged_plaintext(_repo(), HOST) is None
        assert out["persist"]["state"] == "same"
        assert "adds only the tool's account" in out["persist"]["sentence"]
        assert [o["id"] for o in out["netbox"]["existing"]] == [7, 90, 50]
        assert out["netbox"]["dry_run"]["create_count"] == 12
        assert any("SNMP community" in s for s in out["not_doing"])
        assert "_device" not in A.public(out) and "_capture" not in A.public(out)

    def test_persist_names_what_saving_makes_permanent_and_loses(self, lab):
        lab["router"].startup = [l for l in lab["router"].startup if l != "ip cef"] \
            + ["banner motd ^only-in-startup^"]
        lab["router"].running = [l for l in lab["router"].running if l != "ip cef"] \
            + ["ip cef"]
        lab["router"].startup.remove("banner motd ^only-in-startup^")
        lab["router"].startup.append("logging buffered 64000")
        p = _plan(lab)["persist"]
        assert p["state"] == "differs"
        assert p["loses"] == ["logging buffered 64000"], p
        assert "are gone at the next reload" in p["sentence"]

    def test_no_startup_config_says_the_whole_running_config_becomes_the_boot_config(self, lab):
        lab["router"].startup = ["startup-config is not present"]
        assert _plan(lab)["persist"]["state"] == "no_startup"

    def test_a_supplied_account_stored_in_clear_is_refused_and_the_opt_in_offered(self, lab):
        """vrnetlab's own `password 0`: the golden would carry it. Refused by
        default, with the operator's opt-in offered by its own words."""
        lab["router"].load(_config(admin=CLEAR_ADMIN))
        out = _plan(lab)
        assert not out["fingerprint"]
        assert any("'admin' is stored as `password 0`" in b for b in out["blocking"])
        assert out["offer"] == {"key": "convert_supplied", "label": A.CONVERT_LABEL,
                                "account": "admin", "from": "password 0"}
        assert SUPPLIED_PW not in json.dumps(A.public(out))

    def test_chosen_the_conversion_is_in_the_program_and_the_fingerprint(self, lab):
        lab["router"].load(_config(admin=CLEAR_ADMIN))
        out = _plan(lab, convert_supplied=True)
        assert out["blocking"] == [] and out["fingerprint"]
        assert out["program"] == A.masked_program("nmas") + [
            "no username admin",
            "username admin privilege 15 algorithm-type scrypt secret <its same password>"]
        assert "keeps logging in with the password they know" in out["convert"]["sentence"]
        assert SUPPLIED_PW not in json.dumps(A.public(out))
        assert lab["router"].sent == [], "a preview sends nothing"

    @pytest.mark.parametrize("line,named", [
        ("username backup privilege 1 password 7 0822455D0A16", "account 'backup' (`password 7`)"),
        ("username ops privilege 5 password 0 Opspass-4471", "account 'ops' (`password 0`)"),
        ("enable password 0 Enable-Clear-5512", "the enable password (`password 0`)"),
        ("enable password 7 0822455D0A16", "the enable password (`password 7`)"),
    ])
    def test_every_other_reversible_credential_is_refused_by_name_with_no_offer(
            self, lab, line, named):
        lab["router"].running.append(line)
        out = _plan(lab, convert_supplied=True)
        refusal = next(b for b in out["blocking"] if "reversible form" in b)
        assert named in refusal and "does not know these passwords" in refusal
        assert "offer" not in out and not out["fingerprint"]
        value = line.split()[-1]
        assert value not in json.dumps(A.public(out)), "the form is named, never the value"

    def test_snmp_communities_are_the_accepted_exception(self):
        text = _config()
        assert re.search(r"^snmp-server community ", text, re.M), "the exception is exercised"
        assert A.reversible_credentials(text) == []

    def test_a_password_equal_to_the_account_name_is_not_found_in_the_username(self):
        assert A._credential_gate(_config(), "admin", "admin", "", False)["ok"], \
            "the value in a credential slot, never in the username"
        out = A._credential_gate(_config(REAL_ADMIN), "admin", "admin", "", False)
        assert not out["ok"] and out["offer"]

    def test_the_supplied_value_in_clear_elsewhere_is_refused(self):
        text = _config() + f"\ninterface Dialer1\n ppp chap password 0 {SUPPLIED_PW}"
        out = A._credential_gate(text, "admin", SUPPLIED_PW, "", True)
        assert not out["ok"] and "appears in clear" in out["detail"]

    def test_a_line_with_more_than_a_password_is_not_converted(self):
        text = _config(admin=CLEAR_ADMIN) + "\nusername admin autocommand show version"
        out = A._credential_gate(text, "admin", SUPPLIED_PW, "", True)
        assert not out["ok"] and "cannot be stored as a secret" in out["detail"]

    @pytest.mark.parametrize("case,words", [
        ("unknown_list", "no device list named"),
        ("hostname", "calls itself 'r2', not 'r9'"),
        ("writes_off", "NetBox writes are off"),
        ("theirs", "which the tool did not record adding"),
        ("managed", "already in the inventory"),
        ("staged", "nmas-adopt-recover r2"),
    ])
    def test_each_refusal_names_why(self, lab, case, words, monkeypatch):
        kw, host, lst = {}, HOST, LIST
        if case == "unknown_list":
            lst = "Nowhere"
        elif case == "hostname":
            host = "r9"
        elif case == "writes_off":
            from modules import netbox_guard
            monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: False)
        elif case == "theirs":
            lab["router"].running.append("username nmas privilege 1 secret 9 $9$their$s")
        elif case == "managed":
            _adopt_fully(lab)
        elif case == "staged":
            A.write_sidecar(_repo(), HOST, IP, "cisco_xe", "nmas")
            CR.stage_plaintext(_repo(), HOST, "Leftover-Staged-Pass-1")
        sent_before = list(lab["router"].sent)
        out = A.plan(lst, host, mgmt_ip=IP, platform="cisco_iosxe", supplied_username="admin",
                     supplied_password=SUPPLIED_PW, read=lab["router"].reads,
                     netbox_existing=lab["collab"]["netbox_existing"],
                     netbox_preview=lab["collab"]["netbox_preview"], role="router")
        assert not out["fingerprint"]
        assert any(words in b for b in out["blocking"]), out["blocking"]
        assert lab["router"].sent == sent_before, "a refused preview sends nothing"

    def test_a_supplied_login_that_fails_is_a_gate_never_a_fingerprint(self, lab):
        out = _plan(lab, read=lambda d, t: (_ for _ in ()).throw(RuntimeError("refused")))
        assert not out["fingerprint"] and any("could not log in" in b for b in out["blocking"])


def _adopt_fully(lab):
    out = _apply(lab)
    assert out["ok"], out
    return out


class TestTheApply:
    def test_end_to_end_every_step_in_order(self, lab):
        out = _adopt_fully(lab)
        assert [s["step"] for s in out["steps"]] == list(A.APPLY_STEPS)
        assert out["state"] == "adopted"
        router = lab["router"]
        assert [l for l in router.sent if l.strip()] == [
            l for l in router.sent if l.startswith("username nmas privilege 15 algorithm")]
        assert HASHED_ADMIN in router.running, "the supplied account is untouched"
        assert router.saves == 1
        assert "Source: adopt" in _git("log", "-1", "--format=%B")
        assert _git("show", "HEAD:golden/r2.cfg").count("username nmas") == 1
        from modules.nsot import manifest
        _i, entry = manifest.find_by_name(_repo(), HOST)
        assert entry["adopted_at"] and entry["verified_at"] and not entry.get("onboarded_at")
        from modules.device import load_saved_devices
        from modules.nsot.listref import resolve
        row, = [r for r in load_saved_devices(resolve(LIST).csv_path)]
        assert (row["hostname"], row["ip"], row["username"]) == (HOST, IP, "nmas")
        assert out["next"]["open"] == "breakglass_export" and "no entry for r2" in \
            out["next"]["label"]
        assert lab["calls"]["authority"] == "Adopt by op@example.com"

    def test_what_existed_in_netbox_is_adopted_never_created(self, lab):
        from modules import netbox_guard
        netbox_guard.record_created(LIST, "dcim/interfaces", 90, "Gi1")   # an earlier run's
        _adopt_fully(lab)
        held, why = netbox_guard.get_adopted(LIST)
        assert why == "" and sorted((ep, i) for ep, i, _n, _d in held) == [
            ("dcim/devices", 7), ("ipam/ip-addresses", 50)]
        assert not netbox_guard.was_created_by_nmas(LIST, "dcim/devices", 7), \
            "an adopted object never enters the record Remove deletes from"

    def test_the_result_is_recorded_where_it_can_be_read_again(self, lab):
        from modules.nsot import onboard
        _adopt_fully(lab)
        row = onboard.read_runs(_repo())["rows"][0]
        assert (row["kind"], row["device"], row["ok"], row["actor"]) == (
            "adopt", HOST, True, "op@example.com")

    def test_a_moved_device_sends_nothing(self, lab):
        fingerprint = _plan(lab)["fingerprint"]
        lab["router"].running.append("ip domain lookup")
        out = _apply(lab, fingerprint=fingerprint)
        assert not out["ok"] and "moved since the preview" in out["reason"]
        assert fingerprint in out["reason"]
        assert lab["router"].sent == [] and _git("rev-parse", "--verify", "-q", "HEAD") == ""

    def test_a_failed_persist_stops_and_a_rerun_resumes_without_a_second_account(self, lab):
        out = _apply(lab, persist=lambda *a: {"ok": False, "detail": "no startup"})
        assert not out["ok"] and "do not reload" in out["reason"]
        assert [s["step"] for s in out["remaining"]] == ["golden", "netbox", "promote"]
        assert lab["calls"]["netbox"] == 0
        adds = [l for l in lab["router"].sent if l.startswith("username nmas")]
        # The resumed adoption: the preview says so, and the apply adds nothing.
        p = _plan(lab)
        assert p["resume"] and p["program"] == [] and p["fingerprint"]
        out = _apply(lab, fingerprint=p["fingerprint"])
        assert out["ok"], out
        assert "added by an earlier run, nothing sent" in out["steps"][1]["detail"]
        assert [l for l in lab["router"].sent if l.startswith("username nmas")] == adds

    def test_netbox_is_read_before_the_import_or_nothing_is_imported(self, lab):
        reads = []

        def existing(hostname):      # the preview's and the confirm's reads answer
            reads.append(hostname)
            if len(reads) <= 2:
                return {"ok": True, "objects": list(EXISTING), "error": ""}
            return {"ok": False, "objects": [], "error": "NetBox could not be read"}
        out = _apply(lab, fingerprint=_plan(lab, netbox_existing=existing)["fingerprint"],
                     netbox_existing=existing)
        assert not out["ok"] and [r["step"] for r in out["remaining"]] == ["promote"]
        assert "recorded first" in out["reason"] and lab["calls"]["netbox"] == 0

    def test_a_held_device_is_refused_before_anything(self, lab):
        from modules.nsot import device_ops
        import threading
        ready, done = threading.Event(), threading.Event()

        def hold():
            with device_ops.hold(LIST, HOST, "deploy", "someone@example.com"):
                ready.set()
                done.wait(10)
        t = threading.Thread(target=hold)
        t.start()
        try:
            ready.wait(5)
            out = _apply(lab, fingerprint="x")
        finally:
            done.set()
            t.join(5)
        assert out["state"] == "refused" and lab["router"].sent == []


class TestTheOwnersAccountConverted:
    """The operator's opt-in: the supplied account re-sent as a secret with the
    SAME password, proven on a fresh login, and put back when that fails."""

    def _convert(self, lab, **kw):
        lab["router"].load(_config(admin=CLEAR_ADMIN))
        fp = _plan(lab, convert_supplied=True)["fingerprint"]
        assert fp
        return _apply(lab, fingerprint=fp, convert_supplied=True, **kw)

    def test_converted_the_owner_logs_in_with_the_same_password_and_the_golden_holds_a_hash(
            self, lab):
        out = self._convert(lab)
        assert out["ok"], out
        router = lab["router"]
        assert router.passwords["admin"] == SUPPLIED_PW, "the same password"
        line, = [l for l in router.running if l.startswith("username admin ")]
        assert " secret 9 " in line and " password " not in line
        sent = [l for l in router.sent if l.strip()]
        assert sent.index("no username admin") > next(
            i for i, l in enumerate(sent) if l.startswith("username nmas")), \
            "the tool's own account is proven before the owner's is touched"
        golden = _git("show", "HEAD:golden/r2.cfg")
        assert SUPPLIED_PW not in golden and "password 0" not in golden
        step = next(s for s in out["steps"] if s["step"] == "owner_account")
        assert step["ok"] and "re-sent as a secret with the same password" in step["detail"]
        from modules.nsot import onboard
        row = onboard.read_runs(_repo())["rows"][0]
        assert any(s["step"] == "owner_account" and "re-sent as a secret" in s["detail"]
                   for s in row["steps"]), "named in the receipt"

    def test_not_chosen_the_owner_is_not_changed_and_says_so(self, lab):
        out = _adopt_fully(lab)
        step = next(s for s in out["steps"] if s["step"] == "owner_account")
        assert step["ok"] and step["detail"] == "'admin' not changed"
        assert "no username admin" not in lab["router"].sent

    def test_a_failed_login_after_the_conversion_puts_the_original_line_back(self, lab):
        lab["router"].store_as = {"admin": "Not-The-Owners-Password-1"}
        out = self._convert(lab)
        assert not out["ok"] and "original line was put back on the held session" in \
            out["reason"]
        assert CLEAR_ADMIN in lab["router"].running and \
            lab["router"].passwords["admin"] == SUPPLIED_PW, "as it was"
        assert [r["step"] for r in out["remaining"]][:1] == ["profile"]
        from modules import credentials
        assert credentials.resolve(IP)["username"] == "nmas", \
            "the tool's account stays recorded: a second way in"

    def test_a_restore_that_cannot_be_proven_is_the_most_serious_outcome(self, lab):
        lab["router"].store_as = {"admin": "Not-The-Owners-Password-1"}
        lab["router"].refuse = ("password 0",)            # the original line is refused
        out = self._convert(lab)
        assert out["state"] == A.OWNER_AT_RISK and out["reason"].startswith("DANGER")
        assert "username admin privilege 15 password 0 <value>" in out["reason"]
        assert SUPPLIED_PW not in json.dumps(out)
        tool_session_restore = [l for l in lab["router"].sent if "password 0" in l]
        assert len(tool_session_restore) == 2, "held session, then the tool's own session"


def _stores_holding_the_supplied_value() -> list:
    """Every file adoption could have written: the store (DATA_DIR) and the
    list (its working files, staging included), read raw and as Fernet tokens;
    and the repository's WHOLE history as text, since git's objects are
    compressed and a byte scan of `.git` cannot see a committed value."""
    from modules import config
    from modules.device import fernet
    from modules.nsot.listref import resolve
    list_dir = resolve(LIST).data_dir
    paths = [os.path.join(d, f) for root in (config.DATA_DIR, list_dir)
             for d, _, fs in os.walk(root) if os.sep + ".git" not in d + os.sep for f in fs]
    assert len(paths) > 10 and any(p.startswith(list_dir) for p in paths), \
        "the scan read the store AND the list adoption wrote"
    hits = []
    for path in paths:
        data = open(path, "rb").read()
        if SUPPLIED_PW.encode() in data:
            hits.append(path)
        for token in re.findall(rb"gAAAAA[A-Za-z0-9_\-=]+", data):
            try:
                if fernet.decrypt(token).decode() == SUPPLIED_PW:
                    hits.append(path)
            except Exception:                  # noqa: BLE001
                pass
    history = _git("log", "-p", "--all")
    assert "golden/r2.cfg" in history, "the history read holds the golden"
    if SUPPLIED_PW in history:
        hits.append("git history")
    return hits


class TestTheSuppliedCredentialIsNeverWritten:
    def test_after_a_full_adoption_no_file_log_or_result_holds_it(self, lab, caplog):
        with caplog.at_level("DEBUG"):
            out = _adopt_fully(lab)
        assert SUPPLIED_PW not in json.dumps(out) and SUPPLIED_PW not in caplog.text
        assert _stores_holding_the_supplied_value() == []

    def test_after_the_conversion_neither(self, lab, caplog):
        """The supplied password is SENT to the device here, as it must be; it
        is logged masked and lands in no file and no commit."""
        with caplog.at_level("DEBUG"):
            out = TestTheOwnersAccountConverted()._convert(lab)
        assert out["ok"], out
        assert SUPPLIED_PW not in json.dumps(out) and SUPPLIED_PW not in caplog.text
        assert _stores_holding_the_supplied_value() == []

    def test_the_control_a_committed_copy_is_seen(self, lab):
        """Without the conversion, a device whose golden WOULD carry it: forced
        past the gate, the scan finds the value in the history."""
        _adopt_fully(lab)
        from modules.nsot.repo import GoldenItem, save_golden
        save_golden(LIST, [GoldenItem(HOST, _config(admin=CLEAR_ADMIN), mgmt_ip=IP,
                                      platform="cisco_iosxe")],
                    source="adopt", actor="op@example.com", message="control")
        hits = _stores_holding_the_supplied_value()
        assert "git history" in hits and any(h.endswith("golden/r2.cfg") for h in hits), hits


class TestItsOwnRecovery:
    def _unrecorded(self, lab):
        out = _apply(lab, record=lambda ip, u, p: (_ for _ in ()).throw(OSError("store")))
        assert not out["ok"] and out["recover"] == f"nmas-adopt-recover {HOST} --list {LIST}"
        return out

    def test_a_failed_record_keeps_the_copy_and_names_adopts_recovery(self, lab):
        self._unrecorded(lab)
        assert CR.staged_plaintext(_repo(), HOST) and A.read_sidecar(_repo(), HOST)["ip"] == IP

    def test_recovery_records_what_the_device_accepts_then_clears(self, lab):
        from modules import credentials
        self._unrecorded(lab)
        out = A.recover_tool_account(LIST, HOST, actor="op",
                                     verify=lambda d, u, w: {"ok": lab["router"].passwords.get(u)
                                                             == w})
        assert out["state"] == A.RECOVERED, out
        assert credentials.resolve(IP)["username"] == "nmas"
        assert CR.staged_plaintext(_repo(), HOST) is None and A.read_sidecar(_repo(), HOST) is None

    def test_a_refused_staged_password_is_kept_and_a_person_checks(self, lab):
        self._unrecorded(lab)
        out = A.recover_tool_account(LIST, HOST, actor="op", verify=lambda d, u, w: {
            "ok": False, "attempted": True, "error": "Authentication failed"})
        assert out["state"] == A.STAGED_REFUSED and "include ^username nmas" in out["reason"]
        assert CR.staged_plaintext(_repo(), HOST)

    def test_nothing_staged(self, lab):
        assert A.recover_tool_account(LIST, HOST, actor="op")["state"] == A.NOTHING_STAGED

    def test_job_health_names_adopts_recovery_and_a_rotations_stays_its_own(
            self, lab, monkeypatch):
        from modules import job_health
        from modules.nsot.listref import resolve
        # Job health reads under LISTS_DIR (a read never resolves through the
        # accessor that creates a directory); the list is at <tmp>/lab.
        monkeypatch.setattr("modules.config.LISTS_DIR", os.path.dirname(_repo().rstrip(
            os.sep).rsplit(os.sep, 1)[0]))
        self._unrecorded(lab)
        CR.stage_plaintext(_repo(), "r3", "A-Rotation-Staged-Pass-1")       # the control
        rows = job_health.staged_rotation_rows(
            lists=[{"name": LIST, "filename": resolve(LIST).slug}], holder=lambda l, h: None)
        by = {r["device"]: r["action"]["command"] for r in rows}
        assert by == {HOST: f"nmas-adopt-recover {HOST} --list {LIST}",
                      "r3": f"nmas-rotation-recover r3 --list {LIST}"}


class TestTheBreakGlassRowNamesTheNewDevice:
    def test_an_export_without_the_adopted_device_is_stale_for_it(self):
        from modules import job_health
        rows = job_health.breakglass_rows(
            exports={"by_list": {LIST: {"at": 0, "via": "browser", "actor": "op",
                                        "path": "x", "devices": {"r1": "d1"}}}},
            current={LIST: {"r1": "d1", HOST: "d2"}})
        stale, = [r for r in rows if r["state"] == "breakglass_stale"]
        assert stale["devices"] == [HOST] and f"no entry for {HOST}" in stale["detail"]
        assert stale["action"]["open"] == "breakglass_export"


class TestTheImporterHonoursAPreviewTextOnlyInADryRun:
    def test_dry_run_only(self, monkeypatch):
        from modules import netbox_client, netbox_guard
        monkeypatch.setattr("modules.goldens._golden_record",
                            lambda ip, list_name="": {"text": "", "refused": ""})
        dev = {"ip": IP, "hostname": HOST, "preview_config": _config()}
        assert "error" in netbox_client._scan_device_from_golden(dev), \
            "a real import never builds from a caller's text"
        with netbox_guard.dry_run():
            scanned = netbox_client._scan_device_from_golden(dev)
        assert "error" not in scanned and scanned["interfaces"]


PROFILE_LINE = "snmp-server community <redacted:snmp_community> RO"
PROFILE_TRUE = "snmp-server community AdoptProfileValue RO"


def _profile_for_capture(list_name, hostname, platform, role, capture, *, repo="", doc=None):
    """A stand-in for `profile_apply.for_capture` with its shape: the profile's one line is
    to send until the capture holds it."""
    held = PROFILE_TRUE in capture
    return {"applies": True, "why": "" if not held else "already holds every line",
            "commands": [] if held else [PROFILE_TRUE],
            "masked": [] if held else [PROFILE_LINE], "to_send": [], "in_place": [],
            "by_section": {"snmp": []}, "sources": {}, "template": {},
            "unmodeled": [], "fingerprint": "held" if held else "missing",
            "capture_hash": "x"}


class TestTheMonitoringProfileIsApplied:
    """P.9 step (c): adopt applies the network's monitoring profile, computed
    from the capture it reads (`profile_apply.for_capture`, tested on the
    profile lab in test_profile_new_devices.py; here a stand-in with its
    shape, so adopt's plumbing is what is under test): in the program and the
    fingerprint at the preview, sent after the accounts and before the save,
    read back, and in the first golden."""

    LINE = PROFILE_LINE
    TRUE = PROFILE_TRUE

    @pytest.fixture
    def profiled(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.profile_apply.for_capture", _profile_for_capture)
        sent = []

        def send(ip, user, pw, sec, dt, commands):
            sent.append(list(commands))
            lab["router"].running.extend(commands)
            return {"ok": True, "error": ""}
        lab["sent_profile"] = sent
        lab["send"] = send
        return lab

    def test_the_preview_lists_the_profile_lines_masked_and_binds_them(self, profiled):
        out = _plan(profiled)
        assert out["blocking"] == [] and self.LINE in out["program"]
        assert self.TRUE not in json.dumps(A.public(out))
        assert any("monitoring profile" in s for s in out["not_doing"])
        # C930: the save after the profile's step makes its lines permanent too, so the persist
        # sentence names them beside the account.
        assert ("the tool's account and the monitoring profile's 1 line(s)"
                in out["persist"]["sentence"]), out["persist"]["sentence"]

    def test_the_apply_sends_it_after_the_accounts_reads_it_back_and_records_it(self, profiled):
        out = _apply(profiled, send_profile=profiled["send"])
        assert out["ok"] is True, out["reason"]
        steps = [s["step"] for s in out["steps"]]
        assert steps.index("profile") == steps.index("owner_account") + 1
        assert steps.index("profile") < steps.index("persist")
        assert profiled["sent_profile"] == [[self.TRUE]]
        assert "1 line(s) sent and read back" in next(
            s["detail"] for s in out["steps"] if s["step"] == "profile")
        golden = _git("show", f"HEAD:golden/{HOST}.cfg")
        assert self.TRUE in golden, "the first golden records the profile"

    def test_a_line_that_did_not_land_stops_before_the_save(self, profiled):
        out = _apply(profiled, send_profile=lambda *a: {"ok": True, "error": ""})
        assert out["ok"] is False
        row = next(s for s in out["steps"] if s["step"] == "profile")
        assert not row["ok"] and "not every line landed" in row["detail"]
        assert profiled["router"].saves == 0, "nothing saved over a missing line"

    def test_no_profile_sends_nothing_and_says_so(self, lab):
        out = _apply(lab)
        assert out["ok"] is True, out["reason"]
        row = next(s for s in out["steps"] if s["step"] == "profile")
        assert row["ok"] and row["detail"].startswith("not sent: ")


# ---------------------------------------------------------------------------
# Every stop names its own step in the log (C2551 step 3b, mutation-nightly #68)
# ---------------------------------------------------------------------------

def _resumable(lab):
    """A first run stopped at persist: the tool's account is added and recorded, so the
    next run resumes."""
    out = _apply(lab, persist=lambda *a: {"ok": False, "detail": "no startup"})
    assert [r["step"] for r in out["remaining"]] == ["golden", "netbox", "promote"], out
    return out


def _refuse_login(dev):
    raise RuntimeError("Authentication failed")


def _stop_confirm_blocked(lab, monkeypatch, caplog):
    lab["router"].load(_config(admin=CLEAR_ADMIN))      # refused: a password in clear
    return _apply(lab, fingerprint="x")


def _stop_confirm_moved(lab, monkeypatch, caplog):
    return _apply(lab, fingerprint="not-the-previewed-one")


def _stop_account_resumed(lab, monkeypatch, caplog):
    _resumable(lab)
    fingerprint = _plan(lab)["fingerprint"]
    caplog.clear()
    return _apply(lab, fingerprint=fingerprint, verify=lambda d, u, w: {
        "ok": False, "error": "Authentication failed", "attempted": True})


def _stop_account_fresh(lab, monkeypatch, caplog):
    return _apply(lab, record=lambda ip, u, p: (_ for _ in ()).throw(OSError("store")))


def _stop_owner_resumed_no_login(lab, monkeypatch, caplog):
    _resumable(lab)
    router = lab["router"]
    router.running = [CLEAR_ADMIN if l == HASHED_ADMIN else l for l in router.running]
    fingerprint = _plan(lab, convert_supplied=True)["fingerprint"]
    caplog.clear()
    return _apply(lab, fingerprint=fingerprint, convert_supplied=True,
                  open_session=_refuse_login)


def _stop_owner_not_converted(lab, monkeypatch, caplog):
    lab["router"].store_as = {"admin": "Not-The-Owners-Password-1"}
    lab["router"].load(_config(admin=CLEAR_ADMIN))
    fingerprint = _plan(lab, convert_supplied=True)["fingerprint"]
    return _apply(lab, fingerprint=fingerprint, convert_supplied=True)


def _stop_credential_not_read_back(lab, monkeypatch, caplog):
    return _apply(lab, record=lambda ip, u, p: None)       # nothing kept for the address


def _stop_profile_not_applied(lab, monkeypatch, caplog):
    monkeypatch.setattr("modules.nsot.profile_apply.for_capture", _profile_for_capture)
    return _apply(lab, send_profile=lambda *a: {"ok": False, "error": "% Invalid input"})


def _stop_profile_not_read_back(lab, monkeypatch, caplog):
    monkeypatch.setattr("modules.nsot.profile_apply.for_capture", _profile_for_capture)
    return _apply(lab, send_profile=lambda *a: {"ok": True, "error": ""},
                  capture=lambda *a: {"ok": False, "error": "timed out"})


def _stop_persist(lab, monkeypatch, caplog):
    return _apply(lab, persist=lambda *a: {"ok": False, "detail": "no startup"})


def _stop_golden_capture(lab, monkeypatch, caplog):
    return _apply(lab, capture=lambda *a: {"ok": False, "error": "timed out"})


def _stop_golden_save(lab, monkeypatch, caplog):
    monkeypatch.setattr("modules.nsot.repo.save_golden",
                        lambda *a, **k: {"ok": False, "error": "the repository refused"})
    return _apply(lab)


def _stop_netbox_read(lab, monkeypatch, caplog):
    reads = []

    def existing(hostname):             # the preview's and the confirm's reads answer
        reads.append(hostname)
        if len(reads) <= 2:
            return {"ok": True, "objects": list(EXISTING), "error": ""}
        return {"ok": False, "objects": [], "error": "NetBox could not be read"}
    return _apply(lab, fingerprint=_plan(lab, netbox_existing=existing)["fingerprint"],
                  netbox_existing=existing)


def _stop_netbox_import(lab, monkeypatch, caplog):
    return _apply(lab, netbox=lambda *a, **k: {"ok": False, "reason": "NetBox refused it"})


def _stop_netbox_adoption_record(lab, monkeypatch, caplog):
    return _apply(lab, record_adoption=lambda *a, **k: {"ok": False, "error": "read-only"})


def _stop_promote_unkept(lab, monkeypatch, caplog):
    monkeypatch.setattr("modules.nsot.onboard.commit_record", lambda *a, **k: {
        "ok": False, "commit": "", "error": "index.lock exists"})
    return _apply(lab)


def _stop_promote(lab, monkeypatch, caplog):
    return _apply(lab, promote=lambda *a, **k: {"ok": False, "error": "the row was refused"})


#: Each of `_apply`'s seventeen stops: the step it names, how a run reaches it, and the three
#: mutants of run #68 that changed that name in the log line (to None, "XX<name>XX" and upper
#: case). The case id carries their numbers.
STOPS = [
    ("confirm", _stop_confirm_blocked, (161, 165, 166)),
    ("confirm", _stop_confirm_moved, (177, 181, 182)),
    ("account", _stop_account_resumed, (284, 288, 289)),
    ("account", _stop_account_fresh, (356, 360, 361)),
    ("owner_account", _stop_owner_resumed_no_login, (396, 400, 401)),
    ("owner_account", _stop_owner_not_converted, (466, 470, 471)),
    ("profile", _stop_credential_not_read_back, (486, 490, 491)),
    ("profile", _stop_profile_not_applied, (582, 586, 587)),
    ("profile", _stop_profile_not_read_back, (673, 677, 678)),
    ("persist", _stop_persist, (738, 742, 743)),
    ("golden", _stop_golden_capture, (787, 791, 792)),
    ("golden", _stop_golden_save, (894, 898, 899)),
    ("netbox", _stop_netbox_read, (929, 933, 934)),
    ("netbox", _stop_netbox_import, (987, 991, 992)),
    ("netbox", _stop_netbox_adoption_record, (1065, 1069, 1070)),
    ("promote", _stop_promote_unkept, (1179, 1183, 1184)),
    ("promote", _stop_promote, (1193, 1197, 1198)),
]


class TestEveryStopLogsItsOwnStep:
    """The warning an adoption logs when it stops is how an operator reading the log learns
    which step it stopped at (the operator, 2026-11-05: these are not equivalent). Each stop
    is reached for real, and its one warning names its own step and its reason."""

    @pytest.mark.parametrize("step, reach, mutants", STOPS, ids=[
        f"{reach.__name__[len('_stop_'):]}-mutmut_" + "_".join(map(str, mutants))
        for _step, reach, mutants in STOPS])
    def test_kills_adopt__apply_mutmut_stop_log_arguments_each_stop_logs_its_own_step(
            self, lab, monkeypatch, caplog, step, reach, mutants):
        caplog.set_level(logging.WARNING, logger="modules.nsot.adopt")
        out = reach(lab, monkeypatch, caplog)
        assert out["ok"] is False and out["state"] != "refused", out
        lines = [r.getMessage() for r in caplog.records
                 if r.name == "modules.nsot.adopt" and " stopped at " in r.getMessage()]
        assert lines == [f"adopt: {HOST} stopped at {step}: {out['reason']}"]


# ---------------------------------------------------------------------------
# The golden step: the first capture, the manifest entry, the save (group A9)
# ---------------------------------------------------------------------------

def _golden_commit():
    """The one commit that wrote the device's golden (the promote's record commit comes
    after it and touches only the manifest)."""
    sha, = _git("log", "--format=%H", "--", f"golden/{HOST}.cfg").splitlines()
    return sha


def _entries_named(name):
    from modules.nsot import manifest
    return [(i, e) for i, e in manifest.load(_repo())["devices"].items()
            if (e.get("name") or "").lower() == name]


class TestTheGoldenStep:
    """The golden step reads the device as the tool's own account, records the identity
    (address, platform, role, adopted) before the save, and commits the first capture as the
    person who adopted it; each way it can fail stops there and says why."""

    def test_kills_adopt__apply_mutmut_756_to_760_the_first_capture_logs_in_as_the_tool(
            self, lab):
        from modules import credentials
        _adopt_fully(lab)
        held = credentials.resolve(IP)
        (ip, user, pw, secret, device_type), = lab["calls"]["capture"]
        assert (ip, user, device_type) == (IP, "nmas", _plan(lab)["device_type"])
        # Compared, never printed: the tool's password is the login and the enable secret.
        assert (pw == held["password"], secret == held["password"]) == (True, True)

    @pytest.mark.parametrize("answer, detail, reason", [
        ({"ok": False, "error": "timed out reading the running config"},
         "timed out reading the running config", "timed out reading the running config"),
        ({"ok": False}, "", "the device could not be read"),
    ], ids=["named", "unnamed"])
    def test_kills_adopt__apply_mutmut_771_to_798_a_failed_capture_stops_at_the_golden(
            self, lab, answer, detail, reason):
        out = _apply(lab, capture=lambda *a: dict(answer))
        assert [s for s in out["steps"] if s["step"] == "golden"] == [
            {"step": "golden", "ok": False, "detail": detail}]
        assert {s["step"] for s in out["steps"]} == set(A.APPLY_STEPS)
        assert out["reason"] == reason
        assert [r["step"] for r in out["remaining"]] == ["netbox", "promote"]
        assert lab["calls"]["netbox"] == 0 and "golden" not in out
        assert _git("log", "--format=%H", "--", f"golden/{HOST}.cfg") == ""

    @pytest.mark.parametrize("saving, saved, detail, reason", [
        ("raises", {"ok": False, "error": "RuntimeError: the disk is full"},
         "RuntimeError: the disk is full", "RuntimeError: the disk is full"),
        ("refuses", {"ok": False, "error": "the repository refused"},
         "the repository refused", "the repository refused"),
        ("unnamed", {"ok": False}, "", "the golden was not saved"),
    ], ids=["raises", "refuses", "unnamed"])
    def test_kills_adopt__apply_mutmut_861_to_905_a_save_that_fails_stops_at_the_golden(
            self, lab, monkeypatch, saving, saved, detail, reason):
        def save_golden(*a, **k):
            if saving == "raises":
                raise RuntimeError("the disk is full")
            return dict(saved)
        monkeypatch.setattr("modules.nsot.repo.save_golden", save_golden)
        out = _apply(lab)
        assert out["golden"] == saved
        assert [s for s in out["steps"] if s["step"] == "golden"] == [
            {"step": "golden", "ok": False, "detail": detail}]
        assert out["reason"] == reason
        assert [r["step"] for r in out["remaining"]] == ["netbox", "promote"]
        assert lab["calls"]["netbox"] == 0

    def test_kills_adopt__apply_mutmut_836_to_892_the_first_capture_is_committed_as_the_person(
            self, lab):
        out = _adopt_fully(lab)
        sha = _golden_commit()
        body = _git("log", "-1", "--format=%B", sha).splitlines()
        assert body[0] == f"adopt: {HOST} first capture"
        assert "Actor: op@example.com" in body and "Source: adopt" in body
        assert out["golden"]["ok"] is True and out["golden"]["commit"] == sha
        assert [s for s in out["steps"] if s["step"] == "golden"] == [
            {"step": "golden", "ok": True, "detail": sha}]
        header = _git("show", f"{sha}:golden/{HOST}.cfg").splitlines()[0]
        assert header == f"! Golden config — {HOST} ({IP})"

    def test_kills_adopt__apply_mutmut_858_859_no_actor_commits_as_the_tool(self, lab):
        fingerprint = _plan(lab)["fingerprint"]
        out = A.apply(LIST, HOST, mgmt_ip=IP, platform="cisco_iosxe", supplied_username="admin",
                      supplied_password=SUPPLIED_PW, confirmed_fingerprint=fingerprint,
                      actor="", reason="", role="router", **lab["collab"])
        assert out["golden"]["ok"] is True, out
        assert "Actor: nmas" in _git("log", "-1", "--format=%B", _golden_commit()).splitlines()

    def test_kills_adopt__apply_mutmut_848_852_860_a_device_the_manifest_lacks_gets_no_golden(
            self, lab, monkeypatch):
        """`save_golden` never mints an identity here: were the adoption's own manifest write
        lost, the save refuses rather than create the device a second way, and it is refused
        for that reason, the platform the person gave still carried to the save."""
        from modules.nsot import manifest
        real = manifest.upsert_device

        def upsert_device(repo, identity, name, *a, **k):
            if k.get("adopted"):                # the adoption's write, lost
                return {}
            return real(repo, identity, name, *a, **k)
        monkeypatch.setattr(manifest, "upsert_device", upsert_device)
        out = _apply(lab)
        assert out["golden"]["ok"] is False and "is not in the manifest" in out["reason"]
        assert _git("log", "--format=%H", "--", f"golden/{HOST}.cfg") == ""
        assert _entries_named(HOST) == []

    def test_kills_adopt__apply_mutmut_801_812_to_830_a_stopped_save_leaves_one_whole_entry(
            self, lab, monkeypatch):
        """A save that fails leaves the device's entry as adopt recorded it (its name,
        address, platform, role and the adoption), and the next run finds that entry by name
        and saves under it: one identity, never a second."""
        from modules.nsot import repo as R
        real = R.save_golden
        monkeypatch.setattr(R, "save_golden", lambda *a, **k: {"ok": False, "error": "refused"})
        _apply(lab)
        (identity, entry), = _entries_named(HOST)
        assert (entry["mgmt_ip"], entry["platform"], entry.get("role")) == (
            IP, "cisco_iosxe", "router")
        assert entry.get("adopted_at")
        monkeypatch.setattr(R, "save_golden", real)
        out = _apply(lab)
        assert out["ok"], out
        assert [i for i, _e in _entries_named(HOST)] == [identity]
        assert _entries_named(HOST)[0][1].get("role") == "router"

    def test_kills_adopt__apply_mutmut_806_807_a_minted_identity_is_logged_with_name_and_address(
            self, lab, caplog):
        caplog.set_level(logging.INFO, logger="modules.nsot.repo")
        _adopt_fully(lab)
        (identity, _entry), = _entries_named(HOST)
        assert f"repo: adopting {HOST} ({IP}) as {identity}" in [
            r.getMessage() for r in caplog.records if r.name == "modules.nsot.repo"]


# ---------------------------------------------------------------------------
# The NetBox step: the read before the import, the import, the adoption record (group A10)
# ---------------------------------------------------------------------------

ADOPTED = [{"endpoint": ep, "id": i, "name": n} for ep, i, n in EXISTING]
NETBOX_DONE = ("0 created (tagged, recorded as created); 3 that existed recorded as adopted, "
               "never deletable")


def _netbox_rows(out):
    return [s for s in out["steps"] if s["step"] == "netbox"]


def _adoption_record():
    """Each row the adoption record holds for the network, as it is stored."""
    from modules import netbox_guard
    from modules.config import list_slug
    if not os.path.exists(netbox_guard._ADOPTED_FILE):
        return {}
    data = netbox_guard._read_doc(netbox_guard._ADOPTED_FILE)
    return {(ep, r["id"]): r for ep, rows in (data.get(list_slug(LIST)) or {}).items()
            for r in rows}


def _failing_read(answer):
    """The preview's and the confirm's reads of NetBox answer; the apply's gets *answer*."""
    reads = []

    def existing(hostname):
        reads.append(hostname)
        if len(reads) <= 2:
            return {"ok": True, "objects": list(EXISTING), "error": ""}
        return dict(answer)
    return existing


class TestTheNetBoxStep:
    """The NetBox step reads what exists for the device before anything is imported, imports
    as the person under the adoption's authority, records what existed as ADOPTED (who, why,
    on what basis), and says in its result what it did; each way it can fail stops there,
    nothing promoted, and says why."""

    def test_kills_adopt__apply_mutmut_907_953_to_956_964_to_966_the_import_is_the_devices_as_the_person(
            self, lab):
        out = _adopt_fully(lab)
        assert lab["calls"]["existing_for"] == [HOST, HOST, HOST], \
            "the preview's, the confirm's and the apply's reads are all of this device"
        assert lab["calls"]["netbox_args"] == (_repo(), HOST, LIST, "op@example.com")
        assert out["netbox"] == {"ok": True, "created": [], "device_id": 7, "reason": ""}

    def test_kills_adopt__apply_mutmut_1017_to_1057_what_existed_is_recorded_as_adopted(
            self, lab):
        out = _adopt_fully(lab)
        assert out["adopted"] == ADOPTED
        assert _netbox_rows(out) == [{"step": "netbox", "ok": True, "detail": NETBOX_DONE}]
        held = _adoption_record()
        assert sorted(held) == sorted((ep, i) for ep, i, _n in EXISTING)
        assert {(r["device"], r["actor"], r["reason"], r["authority"]) for r in held.values()} \
            == {(HOST, "op@example.com", "taking r2 into management", "Adopt by op@example.com")}

    def test_kills_adopt__apply_mutmut_950_951_1029_to_1031_no_actor_or_reason_says_so(self, lab):
        fingerprint = _plan(lab)["fingerprint"]
        out = A.apply(LIST, HOST, mgmt_ip=IP, platform="cisco_iosxe", supplied_username="admin",
                      supplied_password=SUPPLIED_PW, confirmed_fingerprint=fingerprint,
                      actor="", reason="", role="router", **lab["collab"])
        assert out["ok"], out
        assert lab["calls"]["authority"] == "Adopt by unknown"
        assert {(r["reason"], r["authority"]) for r in _adoption_record().values()} == {
            ("adopted into management", "Adopt by unknown")}

    @pytest.mark.parametrize("answer, detail", [
        ({"ok": False, "objects": [], "error": "NetBox could not be read"},
         "NetBox could not be read"),
        ({"ok": False, "objects": []}, ""),
    ], ids=["named", "unnamed"])
    def test_kills_adopt__apply_mutmut_915_to_947_an_unread_netbox_stops_before_the_import(
            self, lab, answer, detail):
        existing = _failing_read(answer)
        out = _apply(lab, fingerprint=_plan(lab, netbox_existing=existing)["fingerprint"],
                     netbox_existing=existing)
        assert _netbox_rows(out) == [{"step": "netbox", "ok": False, "detail": detail}]
        assert out["reason"] == ("NetBox could not be read before the import, and what "
                                 "existed must be recorded first: " + detail)
        assert [r["step"] for r in out["remaining"]] == ["promote"]
        assert lab["calls"]["netbox"] == 0 and "netbox" not in out and "adopted" not in out

    @pytest.mark.parametrize("answer, detail, reason", [
        ({"ok": False, "reason": "NetBox refused it"}, "NetBox refused it", "NetBox refused it"),
        ({"ok": False}, "", "the NetBox record failed"),
    ], ids=["named", "unnamed"])
    def test_kills_adopt__apply_mutmut_964_971_to_999_a_failed_import_stops_at_netbox(
            self, lab, answer, detail, reason):
        out = _apply(lab, netbox=lambda *a, **k: dict(answer))
        assert out["netbox"] == answer
        assert _netbox_rows(out) == [{"step": "netbox", "ok": False, "detail": detail}]
        assert out["reason"] == reason
        assert [r["step"] for r in out["remaining"]] == ["promote"]
        assert "adopted" not in out and _adoption_record() == {}

    @pytest.mark.parametrize("answer, detail", [
        ({"ok": False, "error": "read-only"}, "read-only"),
        ({"ok": False}, ""),
    ], ids=["named", "unnamed"])
    def test_kills_adopt__apply_mutmut_1044_to_1077_an_unwritten_adoption_record_stops_at_netbox(
            self, lab, answer, detail):
        out = _apply(lab, record_adoption=lambda *a, **k: dict(answer))
        assert out["adopted"] == ADOPTED
        assert _netbox_rows(out) == [{"step": "netbox", "ok": False, "detail": detail}]
        if detail:
            assert out["reason"] == (
                "the import landed and the adoption record could not be written: read-only. "
                "Run adopt again: the import changes nothing twice and the record is taken again")
        assert [r["step"] for r in out["remaining"]] == ["promote"]


# ---------------------------------------------------------------------------
# The promote step: the inventory row, the verified mark, the record's commit (group A11)
# ---------------------------------------------------------------------------

def _row():
    from modules.device import load_saved_devices
    from modules.nsot.listref import resolve
    row, = load_saved_devices(resolve(LIST).csv_path)
    return row


def _promote_rows(out):
    return [s for s in out["steps"] if s["step"] == "promote"]


class TestThePromoteStep:
    """Promotion writes the inventory row the tool's sessions log in from (the tool's account
    and its password, no enable secret), marks the device verified as the person, and commits
    the manifest's last writes in the network's own repository; the result carries both, and
    each way it can fail says why."""

    def test_kills_adopt__apply_mutmut_1099_1107_1110_the_row_holds_the_tools_login(self, lab):
        from modules import credentials
        from modules.device import decrypt_field
        _adopt_fully(lab)
        row, held = _row(), credentials.resolve(IP)
        assert row["username"] == "nmas"
        # Compared, never printed: every session to the device logs in from this row.
        assert (decrypt_field(row["password"]) == held["password"],
                decrypt_field(row["secret"]) == "") == (True, True), \
            "(the row's password is the tool's, the row's enable secret is empty)"

    def test_kills_adopt__apply_mutmut_1096_1104_the_device_is_verified_as_the_person(
            self, lab, caplog):
        caplog.set_level(logging.INFO, logger="modules.nsot.manifest")
        _adopt_fully(lab)
        (identity, _entry), = _entries_named(HOST)
        assert f"manifest: {identity} verified by op@example.com" in [
            r.getMessage() for r in caplog.records if r.name == "modules.nsot.manifest"]

    def test_kills_adopt__apply_mutmut_1111_to_1113_1139_to_1141_1166_to_1170_the_result_carries_both(
            self, lab):
        out = _adopt_fully(lab)
        (_identity, entry), = _entries_named(HOST)
        assert out["promote"] == {"ok": True, "device": HOST, "list": LIST, "csv_row": True,
                                  "verified": True, "error": "",
                                  "verified_at": entry["verified_at"]}
        head = _git("rev-parse", "HEAD")
        assert out["record_commit"] == {"ok": True, "commit": head, "error": ""}
        assert _promote_rows(out) == [{"step": "promote", "ok": True,
                                       "detail": f"in the inventory; recorded in commit {head[:8]}"}]

    def test_kills_adopt__apply_mutmut_1117_the_record_is_committed_in_the_networks_own_repository(
            self, lab, monkeypatch, tmp_path):
        """Every other name (the default network's profile is read too) is another network's
        folder, which holds no repository: a record committed anywhere but here fails."""
        from modules import config
        here, elsewhere = config.get_list_data_dir(LIST), tmp_path / "another-network"
        elsewhere.mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: here if name == LIST else str(elsewhere))
        out = _adopt_fully(lab)
        assert out["record_commit"]["commit"] == _git("rev-parse", "HEAD")
        assert not (elsewhere / "config_repo").exists()

    @pytest.mark.parametrize("answer, detail, reason", [
        ({"ok": False, "error": "the row was refused"}, "the row was refused",
         "the row was refused"),
        ({"ok": False}, "in the inventory", "promotion failed"),
    ], ids=["named", "unnamed"])
    def test_kills_adopt__apply_mutmut_1111_1116_1130_to_1164_1194_to_1204_a_failed_promotion_commits_nothing(
            self, lab, answer, detail, reason):
        out = _apply(lab, promote=lambda *a, **k: dict(answer))
        assert out["promote"] == answer
        assert out["record_commit"] == {"ok": True, "commit": "", "error": ""}
        assert _promote_rows(out) == [{"step": "promote", "ok": False, "detail": detail}]
        assert out["reason"] == reason and out["state"] == "stopped"

    def test_kills_adopt__apply_mutmut_1166_to_1170_1185_to_1192_an_unkept_record_says_what_landed(
            self, lab, monkeypatch):
        unkept = {"ok": False, "commit": "", "error": "index.lock exists"}
        monkeypatch.setattr("modules.nsot.onboard.commit_record", lambda *a, **k: dict(unkept))
        out = _apply(lab)
        assert out["record_commit"] == unkept and out["state"] == "adopted"
        assert _promote_rows(out) == [{"step": "promote", "ok": False,
                                       "detail": "in the inventory"}]
        assert out["reason"] == (
            "r2 is adopted and in the inventory, and its manifest change (the NetBox id and "
            "verified time) was NOT committed: index.lock exists. Nothing was undone. Until "
            ".nsot/manifest.json is committed, an operation that needs a clean repository, "
            "such as Retire, refuses")


# ---------------------------------------------------------------------------
# The account steps: the tool's credential, the owner's verify, the owner's result (groups A2,
# A4 and A6)
# ---------------------------------------------------------------------------

#: The enable secret a privilege-1 owner needs, planted for the test (built by concatenation).
OWNER_ENABLE = "Owner-" + "Enable-Secret-5531"
TOOL_STEPS = ["tool_account", "supplied_session", "local_login", "account_absent", "stage",
              "push", "verify", "record"]
NOT_READ_BACK = (f"the tool's credential for {IP} could not be read back from the store it was "
                 "recorded in")


def _rows(out, step):
    return [s for s in out["steps"] if s["step"] == step]


def _real_verify(lab, monkeypatch):
    """No `verify` injected: the device's own verify (`verify_with_retry`) is what runs, as on
    hardware; this stand-in answers as the router does and keeps what it was asked with."""
    asked = []

    def verify_with_retry(device, username, password, *, secret=None, attempts=3, sleep=None):
        asked.append((device, username, password, secret))
        if lab["router"].passwords.get(username) == password:
            return {"ok": True, "config": lab["router"].text()}
        return {"ok": False, "error": "Authentication failed", "attempted": True}
    monkeypatch.setattr(CR, "verify_with_retry", verify_with_retry)
    return asked


class TestTheAccountSteps:
    """The account step adds the tool's account (or proves the one an earlier run added), and
    says what it did in its row and in the result; the owner's account is verified with the
    owner's enable secret when one was given, and is in the result whatever happened to it;
    and without the tool's credential read back from the store, nothing further is sent."""

    @pytest.mark.parametrize("enable, secret", [
        (OWNER_ENABLE, OWNER_ENABLE),
        ("", SUPPLIED_PW),
    ], ids=["enable_given", "no_enable_the_password"])
    def test_kills_adopt__apply_mutmut_226_to_237_307_318_the_owner_is_verified_with_its_enable_secret(
            self, lab, monkeypatch, enable, secret):
        asked = _real_verify(lab, monkeypatch)
        lab["router"].load(_config(admin=CLEAR_ADMIN))
        fingerprint = _plan(lab, convert_supplied=True)["fingerprint"]
        out = _apply(lab, fingerprint=fingerprint, convert_supplied=True, supplied_enable=enable,
                     verify=None)
        assert out["ok"], out
        owner = [(d and d.get("ip"), u, w == SUPPLIED_PW, s == secret)
                 for d, u, w, s in asked if u == "admin"]
        assert owner == [(IP, "admin", True, True)], \
            "(one fresh login as the owner, with its password, enabling with its enable secret)"

    def test_kills_adopt__apply_mutmut_213_to_225_an_entry_without_a_login_reads_as_empty(
            self, lab, monkeypatch):
        """A resumed run proves the tool's account from the store; an entry there with no
        username or password is proved as empty values, never as None or anything else, and
        nothing further is sent."""
        from modules import credentials
        _resumable(lab)
        fingerprint = _plan(lab)["fingerprint"]
        real_resolve, real_plan, planned = credentials.resolve, A._plan, []

        def plan(*a, **k):
            out = real_plan(*a, **k)
            planned.append(True)
            return out
        monkeypatch.setattr(A, "_plan", plan)
        monkeypatch.setattr(credentials, "resolve",
                            lambda ip: {"ok": True} if planned else real_resolve(ip))
        asked = []

        def verify(dev, user, pw):
            asked.append((user, pw))
            return {"ok": True}
        out = _apply(lab, fingerprint=fingerprint, verify=verify)
        assert asked == [("", "")]
        assert _rows(out, "account") == [{"step": "account", "ok": True, "detail": (
            "'' logs in on a fresh session: added by an earlier run, nothing sent")}]
        assert out["reason"] == NOT_READ_BACK

    @pytest.mark.parametrize("resumed", [False, True], ids=["fresh", "resumed"])
    def test_kills_adopt__apply_mutmut_238_422_423_no_conversion_leaves_no_owner_result(
            self, lab, resumed):
        fingerprint = None
        if resumed:
            _resumable(lab)
            fingerprint = _plan(lab)["fingerprint"]
        out = _apply(lab, fingerprint=fingerprint)
        assert out["ok"], out
        assert "owner_account" in out and out["owner_account"] is None

    def test_kills_adopt__apply_mutmut_421_to_423_a_converted_owner_is_in_the_result(self, lab):
        out = TestTheOwnersAccountConverted()._convert(lab)
        assert out["ok"], out
        row, = _rows(out, "owner_account")
        assert out["owner_account"] == {"state": A.OWNER_CONVERTED, "detail": row["detail"]}

    def test_kills_adopt__apply_mutmut_322_to_330_364_to_367_the_added_account_is_in_the_result(
            self, lab):
        out = _adopt_fully(lab)
        assert sorted(out["account"]) == ["state", "steps"]
        assert out["account"]["state"] == A.ADDED
        assert [(s["name"], s["ok"]) for s in out["account"]["steps"]] == [
            (name, True) for name in TOOL_STEPS]
        assert _rows(out, "account") == [{"step": "account", "ok": True, "detail": (
            "'nmas' added, verified and recorded; 'admin' was not changed. Persistence not "
            "yet verified")}]

    def test_kills_adopt__apply_mutmut_297_322_to_330_336_338_to_347_357_an_unrecorded_account_stops_naming_its_recovery(
            self, lab):
        out = TestItsOwnRecovery()._unrecorded(lab)
        staged_at = os.path.join(_repo(), CR.STAGING_REL, f"{HOST}.enc")
        reason = ("'nmas' was added and verified on the device, but recording it FAILED: "
                  f"OSError: store. The staged copy at {staged_at} is the ONLY copy of that "
                  "account's password: keep it, and settle it with nmas-adopt-recover r2 --list "
                  "Lab. The supplied account 'admin' still logs in, so the device is reachable")
        assert out["reason"] == reason
        assert _rows(out, "account") == [{"step": "account", "ok": False, "detail": reason}]
        assert sorted(out["account"]) == ["state", "steps"]
        assert out["account"]["state"] == A.ADDED_NOT_RECORDED
        assert [(s["name"], s["ok"]) for s in out["account"]["steps"]] == [
            (name, name != "record") for name in TOOL_STEPS]
        assert [r["step"] for r in out["remaining"]] == [
            "owner_account", "profile", "persist", "golden", "netbox", "promote"]

    def test_kills_adopt__apply_mutmut_459_481_to_483_a_restored_owner_stops_and_says_so(
            self, lab):
        lab["router"].store_as = {"admin": "Not-The-Owners-Password-1"}
        out = TestTheOwnersAccountConverted()._convert(lab)
        assert out["owner_account"]["state"] == A.OWNER_RESTORED
        detail = out["owner_account"]["detail"]
        assert detail.startswith("converting 'admin' failed")
        assert _rows(out, "owner_account") == [
            {"step": "owner_account", "ok": False, "detail": detail}]
        assert out["reason"] == detail + ". Nothing further was done"
        assert out["state"] == "stopped", "put back as it was: not at risk"

    def test_kills_adopt__apply_mutmut_451_to_480_a_conversion_that_returns_nothing_did_not_run(
            self, lab, monkeypatch):
        monkeypatch.setattr(A, "_convert_owner", lambda *a, **k: None)
        out = TestTheOwnersAccountConverted()._convert(lab)
        assert out["owner_account"] is None
        assert _rows(out, "owner_account") == [
            {"step": "owner_account", "ok": False, "detail": "the conversion did not run"}]
        assert out["reason"] == ". Nothing further was done"
        assert out["state"] == "stopped"
        assert [r["step"] for r in out["remaining"]][:1] == ["profile"]

    @pytest.mark.parametrize("held", [
        None,
        {"ok": True, "username": "nmas", "password": ""},
        {"ok": True, "username": "", "password": "Half-" + "Kept-Pass-2"},
    ], ids=["nothing_kept", "no_password", "no_username"])
    def test_kills_adopt__apply_mutmut_485_to_493_a_credential_not_read_back_stops_before_the_profile(
            self, lab, monkeypatch, held):
        if held is not None:
            monkeypatch.setattr("modules.credentials.resolve", lambda ip: dict(held))
        out = _apply(lab, record=lambda ip, u, p: None)       # nothing kept for the address
        assert out["reason"] == NOT_READ_BACK
        assert [r["step"] for r in out["remaining"]] == [
            "profile", "persist", "golden", "netbox", "promote"]
        assert lab["router"].saves == 0 and lab["calls"]["capture"] == []


# ---------------------------------------------------------------------------
# The profile not sent, and the persist step (groups A7a and A8)
# ---------------------------------------------------------------------------

SAVED = {"ok": True, "state": "persisted", "detail": "the startup config carries it"}
NOT_SAVED_TAIL = (". The tool's account is in the RUNNING config only: do not reload the "
                  "device. Run adopt again to resume; it proves the account and saves again")


class TestTheProfileNotSentAndThePersistStep:
    """A profile with nothing to send says why in its row; the save runs as the tool's own
    account, its answer is in the result and in the rotation record as adopt's; a save that
    fails stops there and says not to reload."""

    @pytest.mark.parametrize("answer, detail", [
        ({"applies": False, "commands": []}, "not sent: nothing to send"),
        ({"applies": False, "why": "the network has no monitoring profile", "commands": []},
         "not sent: the network has no monitoring profile"),
        ({"applies": True, "why": "the device holds the profile's 4 line(s)", "commands": [],
          "fingerprint": "held"}, "the device holds the profile's 4 line(s)"),
        ({"applies": True, "commands": [], "fingerprint": "held"}, "already holds every line"),
    ], ids=["no_profile", "no_profile_why", "held_why", "held"])
    def test_kills_adopt__apply_mutmut_495_to_532_an_unsent_profile_says_why(
            self, lab, monkeypatch, answer, detail):
        monkeypatch.setattr("modules.nsot.profile_apply.for_capture",
                            lambda *a, **k: dict(answer))
        out = _apply(lab)
        assert out["ok"], out
        assert _rows(out, "profile") == [{"step": "profile", "ok": True, "detail": detail}]

    def test_kills_adopt__apply_mutmut_693_to_718_the_save_is_the_tools_and_is_recorded(
            self, lab, monkeypatch):
        from modules import credentials
        from modules.nsot import onboard
        asked, recorded, real = [], [], onboard._record_native_persist

        def persist(ip, user, pw, sec, dt):
            asked.append((ip, user, pw, sec, dt))
            lab["collab"]["persist"](ip, user, pw, sec, dt)
            return dict(SAVED)

        def record(*a, **k):
            recorded.append((a, k))
            return real(*a, **k)
        monkeypatch.setattr(onboard, "_record_native_persist", record)
        out = _apply(lab, persist=persist)
        assert out["ok"], out
        held = credentials.resolve(IP)
        (ip, user, pw, sec, dt), = asked
        assert (ip, user, dt) == (IP, "nmas", _plan(lab)["device_type"])
        # Compared, never printed: the tool's password is the login and the enable secret.
        assert (pw == held["password"], sec == held["password"]) == (True, True)
        assert out["persist"] == SAVED
        assert recorded == [((HOST, SAVED, "op@example.com"), {"via": "adopt", "list_name": LIST})]
        assert _rows(out, "persist") == [
            {"step": "persist", "ok": True, "detail": "the startup config carries it"}]

    @pytest.mark.parametrize("answer, detail, reason", [
        ({"ok": False, "detail": "no startup"}, "no startup", "no startup" + NOT_SAVED_TAIL),
        ({"ok": False}, "", "the save could not be confirmed" + NOT_SAVED_TAIL),
    ], ids=["named", "unnamed"])
    def test_kills_adopt__apply_mutmut_722_to_754_a_failed_save_stops_and_says_do_not_reload(
            self, lab, answer, detail, reason):
        out = _apply(lab, persist=lambda *a: dict(answer))
        assert out["persist"] == answer
        assert _rows(out, "persist") == [{"step": "persist", "ok": False, "detail": detail}]
        assert out["reason"] == reason
        assert [r["step"] for r in out["remaining"]] == ["golden", "netbox", "promote"]


# ---------------------------------------------------------------------------
# The result: its skeleton, a stop's rows, the confirm and the success tail (groups A0, A1, A12)
# ---------------------------------------------------------------------------

#: The keys every result of `_apply` carries on a stop at the confirm (the network's repository
#: is known by then, so the run is recorded): no more, no fewer.
STOPPED_KEYS = {"ok", "device", "list", "state", "steps", "remaining", "reason",
                "tool_account", "supplied_account", "actor", "run_record"}


def _did_not_run(steps, why):
    return ([{"step": s, "ok": False, "detail": "did not run"} for s in steps],
            [{"step": s, "why": why} for s in steps])


def _moved_reason(confirmed, now):
    return (f"the device or the plan moved since the preview (confirmed {confirmed}, now "
            f"{now}): nothing was sent. Preview again and confirm what it shows")


class TestTheResult:
    """What an adoption's result says, stopped or done: which device, which network, who and
    as which accounts, where its run was recorded; every step a stop did not run, with why; the
    confirm's own refusals, word for word; and, adopted, what was done and what comes next."""

    def test_kills_adopt__apply_mutmut_4_5_7_to_14_19_20_22_to_27_63_75_to_83_a_stop_says_who_what_and_where(
            self, lab):
        from modules.nsot import onboard
        out = _apply(lab, fingerprint="not-the-previewed-one")
        assert set(out) == STOPPED_KEYS, sorted(out)
        assert {k: out[k] for k in ("ok", "device", "list", "state", "tool_account",
                                    "supplied_account", "actor", "run_record")} == {
            "ok": False, "device": HOST, "list": LIST, "state": "stopped",
            "tool_account": "nmas", "supplied_account": "admin", "actor": "op@example.com",
            "run_record": {"ok": True, "error": ""}}
        row, = onboard.read_runs(_repo())["rows"]
        assert (row["kind"], row["list"], row["device"], row["ok"]) == ("adopt", LIST, HOST, False)

    def test_kills_adopt__apply_mutmut_108_109_113_to_116_122_123_a_stop_names_every_step_it_did_not_run(
            self, lab):
        out = _apply(lab, fingerprint="not-the-previewed-one")
        assert (out["steps"], out["remaining"]) == _did_not_run(A.APPLY_STEPS, out["reason"])
        out = _apply(lab, persist=lambda *a: {"ok": False, "detail": "no startup"})
        rest = ("golden", "netbox", "promote")
        assert [s["ok"] for s in out["steps"][:5]] == [True, True, True, True, False], out
        assert (out["steps"][5:], out["remaining"]) == _did_not_run(rest, out["reason"])

    def test_kills_adopt__apply_mutmut_40_each_step_is_noted_on_the_hold(self, lab, monkeypatch):
        """A stepper drawing the adoption reads the hold's trail: each step is noted by its
        name as it is reached, the tool account's own steps before the account's (the
        promotion reads the trail before its own step)."""
        from modules.nsot import device_ops, onboard
        real, seen = onboard.promote_device, []

        def promote_device(*a, **k):
            seen.append([s for s, _at in device_ops.holder(LIST, HOST)["progress"]["trail"]])
            return real(*a, **k)
        monkeypatch.setattr(onboard, "promote_device", promote_device)
        _adopt_fully(lab)
        assert seen == [["started", "confirm", *TOOL_STEPS, "account", "owner_account",
                         "profile", "persist", "golden", "netbox"]]

    def test_kills_adopt__apply_mutmut_131_136_150_the_confirm_reads_as_the_person_gave(self, lab):
        """The confirm's plan is made with what the person gave: the device it reads carries
        their enable secret, and NetBox's dry run is asked as them."""
        from modules.device import decrypt_field
        reads, actors = [], []

        def read(device, tool):
            reads.append(device)
            return lab["router"].reads(device, tool)

        def netbox_preview(*a, **k):
            actors.append(k.get("actor"))
            return lab["collab"]["netbox_preview"](*a, **k)
        fingerprint = _plan(lab, supplied_enable=OWNER_ENABLE, read=read,
                            netbox_preview=netbox_preview)["fingerprint"]
        out = _apply(lab, fingerprint=fingerprint, supplied_enable=OWNER_ENABLE, read=read,
                     netbox_preview=netbox_preview)
        assert out["ok"], out
        # Compared, never printed: the preview's read and the confirm's.
        assert [decrypt_field(d["secret"]) == OWNER_ENABLE for d in reads] == [True, True]
        assert actors == ["preview", "op@example.com"]

    def test_kills_adopt__apply_mutmut_162_to_164_167_to_173_a_blocked_confirm_says_every_reason(
            self, lab):
        lab["router"].load(_config(admin=CLEAR_ADMIN).replace(f"hostname {HOST}\n",
                                                              f"hostname {HOST}-old\n"))
        blocking = _plan(lab)["blocking"]
        assert len(blocking) == 2 and blocking[0] == (
            f"the device calls itself '{HOST}-old', not '{HOST}': adopt it under the name it "
            "has") and "'admin' is stored as `password 0`" in blocking[1], blocking
        out = _apply(lab, fingerprint="x")
        assert out["reason"] == "refused, and nothing was sent: " + "; ".join(blocking)
        assert (out["steps"], out["remaining"]) == _did_not_run(A.APPLY_STEPS, out["reason"])
        assert lab["router"].sent == []

    @pytest.mark.parametrize("confirmed", ["", "not-the-previewed-one"], ids=["none", "another"])
    def test_kills_adopt__apply_mutmut_184_185_188_to_190_a_moved_device_names_both_fingerprints(
            self, lab, confirmed):
        now = _plan(lab)["fingerprint"]
        out = _apply(lab, fingerprint=confirmed)
        assert out["reason"] == _moved_reason(confirmed or "(none)", now)
        assert lab["router"].sent == []

    def test_kills_adopt__apply_mutmut_200_202_203_the_confirm_step_names_what_was_previewed(
            self, lab):
        fingerprint = _plan(lab)["fingerprint"]
        out = _apply(lab, fingerprint=fingerprint)
        assert out["steps"][0] == {"step": "confirm", "ok": True,
                                   "detail": f"the device is as previewed ({fingerprint})"}

    def test_kills_adopt__apply_mutmut_1210_to_1212_1222_to_1229_an_adoption_says_what_it_did_and_what_is_next(
            self, lab):
        out = _adopt_fully(lab)
        assert out["reason"] == (f"{HOST} adopted: the tool logs in as 'nmas', and 'admin' was "
                                 "not changed and is used by nothing")
        assert out["next"] == {"label": (f"Export the break-glass record: it holds no entry "
                                         f"for {HOST} until you do"),
                               "open": "breakglass_export", "list": LIST}
        assert out["then"] == "Seed its intent from the golden, on its Device page"
