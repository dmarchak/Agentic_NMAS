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
    calls = {"netbox": 0, "existing": 0}
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
        return {"ok": True, "objects": list(EXISTING), "error": ""}

    def netbox(repo, hostname, list_name, *, actor, authority):
        calls["netbox"] += 1
        calls["authority"] = authority
        return {"ok": True, "created": [], "device_id": 7, "reason": ""}

    collab = {"read": router.reads, "open_session": lambda dev: Session(router),
              "verify": verify, "persist": persist,
              "capture": lambda ip, u, p, s, dt: {"ok": True, "config": router.text()},
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
        assert p["only_startup"] == ["logging buffered 64000"], p
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
        assert stale["device"] == HOST and "has no entry for it" in stale["detail"]
        assert stale["action"]["open"] == "breakglass_export"


class TestTheImporterHonoursAPreviewTextOnlyInADryRun:
    def test_dry_run_only(self, monkeypatch):
        from modules import netbox_client, netbox_guard
        monkeypatch.setattr("modules.ai_assistant._golden_record",
                            lambda ip, list_name="": {"text": "", "refused": ""})
        dev = {"ip": IP, "hostname": HOST, "preview_config": _config()}
        assert "error" in netbox_client._scan_device_from_golden(dev), \
            "a real import never builds from a caller's text"
        with netbox_guard.dry_run():
            scanned = netbox_client._scan_device_from_golden(dev)
        assert "error" not in scanned and scanned["interfaces"]


class TestTheMonitoringProfileIsApplied:
    """P.9 step (c): adopt applies the network's monitoring profile, computed
    from the capture it reads (`profile_apply.for_capture`, tested on the
    profile lab in test_profile_new_devices.py; here a stand-in with its
    shape, so adopt's plumbing is what is under test): in the program and the
    fingerprint at the preview, sent after the accounts and before the save,
    read back, and in the first golden."""

    LINE = "snmp-server community <redacted:snmp_community> RO"
    TRUE = "snmp-server community AdoptProfileValue RO"

    @pytest.fixture
    def profiled(self, lab, monkeypatch):
        def for_capture(list_name, hostname, platform, role, capture, *, repo="", doc=None):
            held = self.TRUE in capture
            return {"applies": True, "why": "" if not held else "already holds every line",
                    "commands": [] if held else [self.TRUE],
                    "masked": [] if held else [self.LINE], "to_send": [], "in_place": [],
                    "by_section": {"snmp": []}, "sources": {}, "template": {},
                    "unmodeled": [], "fingerprint": "held" if held else "missing",
                    "capture_hash": "x"}
        monkeypatch.setattr("modules.nsot.profile_apply.for_capture", for_capture)
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
