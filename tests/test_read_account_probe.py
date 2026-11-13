"""The read-only account probe (scripts/nmas-read-account-probe; C2657's rollout, the operator's
order of 2026-11-13: "a measured probe, signing in AS the read-only account: every AI read shape
answers; `configure terminal`, `clear counters`, `debug` and `show running-config` are refused").

The probe MEASURES a device, so its tests hold its deciding, never a claim about devices: the
device is a stand-in at the probe's session seam (`OPEN`), answering from real captures
(tests/fixtures/operational/*__show_foobar.txt for IOS's refusal, r2__show_interfaces_Loopback0.txt
for a read's answer, tests/fixtures/console/ for a configuration prompt and `end`'s answer,
tests/fixtures/tier2/ for a `[confirm]`), each with at most an echoed command or a prompt added.
Two answers are NOT captures, and say so where they are used: the prompt alone after `n`, and
`debug ?`'s help listing (no capture of a `?` listing exists in tests/fixtures).

The credential store is this test's own (a temporary folder): the deploy login and the
read-only account are both set in it, so the session's login is the store's, resolved by the
reads engine's own `reads.read_account_for`.

IPv6 is held beside IPv4: the device's intent carries an IPv6 address and an IPv6 BGP peer, and
the IPv6 read shapes are filled and sent like the IPv4 ones.
"""

import calendar
import contextlib
import importlib.util
import json
import logging
import os
import types
from importlib.machinery import SourceFileLoader

import pytest

from modules import credentials as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
PATH = os.path.join(ROOT, "scripts", "nmas-read-account-probe")


def _load():
    spec = importlib.util.spec_from_file_location(
        "readaccountprobe", PATH, loader=SourceFileLoader("readaccountprobe", PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_LOADED = []


def _tool():
    """The probe, loaded once at first use, never at collection: each test is red, not the
    file, where the probe is absent (as tests/test_nmas_pregate.py loads its tool)."""
    if not _LOADED:
        _LOADED.append(_load())
    return _LOADED[0]


class _Probe:
    """The probe's names, read from the module at each use (so a patch of the module is seen)."""

    def __getattr__(self, name):
        return getattr(_tool(), name)


P = _Probe()

NET, HOST = "net", "edge1"
RO_NAME, RO_PW = "mercury-ro", "ReadOnly-Not-Real-4417"
DEPLOY_PW = "Deploy-Not-Real-9025"
MAC = "0000.5e00.5301"                     # RFC 7042's documentation range


def _fix(*parts):
    with open(os.path.join(FIX, *parts), encoding="utf-8") as fh:
        return fh.read()


#: IOS-XE's refusal, as captured (`show foobar` on an IOS-XE router).
INVALID = _fix("operational", "r3__show_foobar.txt")
#: A read's answer, as captured.
ANSWER = _fix("operational", "r2__show_interfaces_Loopback0.txt")
#: The `[confirm]` IOS-XE asked for `clear counters <interface>`, as captured.
CONFIRM = _fix("tier2", "r2__clear_counters_Loopback0.txt")


def _console(command):
    """What the console answered *command* with: its echo, then the reply, up to the next send
    (tests/fixtures/console/README.md: `>>> send '...'` is what was sent)."""
    for name in ("s5-kickstart-take-syslog.txt", "s5-kickstart-take-copy-echo.txt"):
        text = _fix("console", name)
        mark = f">>> send '{command}\\r'\n"
        if mark in text:
            return text.split(mark, 1)[1].split(">>> send", 1)[0]
    raise AssertionError(f"no capture of {command!r}")


CONFIG_MODE = _console("configure terminal")
END_ANSWER = _console("end")


def refused(command):
    """The device's refusal of *command*: its echo, the captured refusal, the prompt."""
    return f"{command}\n{INVALID}\n{HOST}>"


INTENT = {"platform": "cisco_iosxe",
          "interfaces": [{"name": "GigabitEthernet1", "ipv4": "192.0.2.21 255.255.255.0",
                          "ipv6": ["2001:db8::21/64", "fe80::21/64"]}],
          "routing": {"bgp": {"neighbors": ["neighbor 192.0.2.22 remote-as 65001",
                                            "neighbor 2001:db8::22 remote-as 65001"]}},
          "telemetry": [{"subscription": 101}]}
GOLDEN = "interface GigabitEthernet1\n ip address 192.0.2.21 255.255.255.0\n"


class Device:
    """A device at the probe's session seam: reads (`send_command`) answered from *reads*,
    raw sends from *sends*, text typed without Enter from *bare*; everything recorded."""

    base_prompt = HOST

    def __init__(self, log, reads=None, sends=None, bare=None):
        self.log, self.reads = log, reads or {}
        self.sends = {c: refused(c) for c in ("show running-config", "configure terminal",
                                             "clear counters")}
        self.sends.update(sends or {})
        self.bare = {"debug ?": refused("debug ?")}
        self.bare.update(bare or {})
        self.pending = ""

    def send_command(self, cmd, **kw):
        self.log.append(("read", cmd))
        return self.reads.get(cmd, ANSWER)

    def send_command_timing(self, cmd, **kw):
        self.log.append(("send", cmd))
        # Anything not scripted answers the prompt alone, so a wrong send is read by the
        # tests' assertions on the log, never a crash.
        return self.sends.get(cmd, f"\n{HOST}#")

    def write_channel(self, text):
        self.log.append(("type", text))
        self.pending = self.bare.get(text, f"\n{HOST}#")

    def read_channel_timing(self, **kw):
        got, self.pending = self.pending, ""
        return got

    def enable(self):
        self.log.append(("enable", ""))

    def disconnect(self):
        self.log.append(("disconnect", ""))


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """The credential store (deploy login and read-only account), the inventory, the committed
    intent and golden, the hold recorded, and the session seam; nothing else reached."""
    monkeypatch.setattr(C, "_FILE", str(tmp_path / "credential_profiles.json"))
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    C.save_profile("default", username="netops", password=DEPLOY_PW)
    C.set_read_account("default", RO_NAME, RO_PW, actor="op@example.com", verified="access")
    from modules.inventory.netbox_source import _encrypt_for_shape
    dev = {"hostname": HOST, "ip": "192.0.2.21", "device_type": "cisco_xe", "role": "router",
           "platform": "cisco_iosxe", "username": "netops",
           "password": _encrypt_for_shape(DEPLOY_PW), "secret": _encrypt_for_shape(DEPLOY_PW)}
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path: [dict(dev)])
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: types.SimpleNamespace(csv_path="unused", repo_dir="unused"))
    state = {"intent": dict(INTENT), "golden": GOLDEN, "log": [], "opened": [], "device": None}
    # Where the probe is absent (its commit's parent), nothing is patched: each test's own
    # use of it then fails, so the test is red rather than its setup.
    probe = _tool() if os.path.exists(PATH) else None
    if probe:
        monkeypatch.setattr(probe, "_committed", lambda network, host: (
            {HOST: state["intent"]}, {HOST: state["golden"]}))

    @contextlib.contextmanager
    def hold(list_name, hostname, operation, actor, detail="", ip=""):
        state["log"].append(("hold", f"{list_name}/{hostname} {operation} {actor}"))
        try:
            yield
        finally:
            state["log"].append(("release", hostname))

    monkeypatch.setattr("modules.nsot.device_ops.hold", hold)

    def opener(params):
        state["opened"].append(params)
        state["log"].append(("open", params["username"]))
        if isinstance(state["device"], Exception):
            raise state["device"]
        return state["device"]

    if probe:
        monkeypatch.setattr(probe, "OPEN", opener)
        monkeypatch.setattr(probe, "in_backup_window", lambda now=None: False)
    state["dir"] = tmp_path
    return state


def _plan(**given):
    return P.plan(NET, HOST, dict({"mac": MAC}, **given))


def _run(lab, device, **given):
    lab["device"] = device
    p = _plan(**given)
    return p, P.run(p, P._inventory(NET)[HOST], "op@example.com", {}, 32 * 1024)


def _main(*argv):
    return P.main(["--network", NET, "--device", HOST, "--mac", MAC, *argv])


def _records(lab):
    folder = lab["dir"] / "probes" / "read-account"
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


# ---------------------------------------------------------------------------- the preview

class TestThePreview:
    def test_the_preview_touches_nothing_and_names_the_account_not_its_password(
            self, lab, capsys):
        assert _main() == 0
        out = capsys.readouterr().out
        assert lab["opened"] == [] and lab["log"] == [], "nothing opened, nothing held"
        assert _records(lab) == [], "nothing recorded"
        assert f"signs in as {RO_NAME}, the read-only account of profile default" in out
        assert "read-account:profile:default" in out
        assert RO_PW not in out and DEPLOY_PW not in out
        p = _plan()
        assert f"hash: {p['hash']}" in out
        lines = [ln.strip() for ln in out.splitlines()]
        for n, command in enumerate(p["program"], 1):
            assert f"{n:2d}. {command}".strip() in " ".join(lines), command
        tail = [c for c in p["program"]][-4:]
        assert tail == ["show running-config", "configure terminal", "clear counters", "debug ?"]

    def test_every_read_is_the_ai_read_sets_own_rendered_by_its_check(self, lab):
        """The reads come from `router_reads.SHAPES` through `fixit_reads.FAMILY` (one home),
        each rendered by `read_loop.check`: the configuration class's forms left out, the
        other dialect's form not asked, the arguments filled from intent and the golden."""
        from modules.ai import router_reads as RR

        p = _plan()
        sent = {r["op"]: r["command"] for r in p["reads"] if r.get("command")}
        shapes = [s[0] for s in RR.SHAPES if s[4] != "configuration"]
        assert [r["op"] for r in p["reads"]] == shapes
        assert "running_config" not in sent and "running_config_interface" not in sent
        assert sent["interfaces"] == "show interfaces GigabitEthernet1"
        assert sent["route"] == "show ip route 192.0.2.21"
        assert sent["route6"] == "show ipv6 route 2001:db8::21", "the global, not link-local"
        assert sent["bgp_neighbor"] == "show ip bgp neighbors 192.0.2.22"
        assert sent["bgp_neighbor6"] == "show bgp ipv6 unicast neighbors 2001:db8::22"
        assert sent["telemetry_receiver"] == "show telemetry ietf subscription 101 receiver"
        assert sent["mac"] == f"show mac address-table address {MAC}"
        assert sent["ospfv3_neighbor"] == "show ospfv3 neighbor"
        other = {r["op"]: r for r in p["reads"] if r.get("result") == "other platform"}
        assert list(other) == ["ipv6_ospf_neighbor"], other

    def test_a_shape_with_nothing_to_fill_is_not_measured_never_dropped(self, lab):
        p = P.plan(NET, HOST, {})
        rows = {r["op"]: r for r in p["reads"]}
        assert rows["mac"]["result"] == P.NOT_MEASURED and "--mac" in rows["mac"]["why"]
        lab["intent"] = dict(INTENT, routing={})
        rows = {r["op"]: r for r in P.plan(NET, HOST, {"mac": MAC})["reads"]}
        assert rows["bgp_neighbor"]["result"] == P.NOT_MEASURED
        assert rows["bgp_neighbor6"]["result"] == P.NOT_MEASURED

    def test_an_argument_the_ais_check_refuses_is_not_measured_and_said(self, lab):
        rows = {r["op"]: r for r in _plan(interface="GigabitEthernet9")["reads"]}
        assert rows["interfaces"]["result"] == P.NOT_MEASURED
        assert "GigabitEthernet9 is not an interface" in rows["interfaces"]["why"]

    def test_the_hash_binds_the_program_and_the_account(self, lab):
        first = _plan()["hash"]
        assert _plan()["hash"] == first, "the same program hashes alike"
        assert _plan(interface="GigabitEthernet1")["hash"] == first, "the default named"
        lab["golden"] = GOLDEN + "interface GigabitEthernet2\n"
        assert _plan(interface="GigabitEthernet2")["hash"] != first, "another argument"
        C.set_read_account("default", RO_NAME, "ReadOnly-Not-Real-5562", actor="op@example.com",
                           verified="access")
        assert _plan()["hash"] == first, "a password replaced is not in the program"
        C.save_profile("role:router", username="netops2", password="Deploy-Not-Real-7781")
        C.set_read_account("role:router", "mercury-ro2", RO_PW + "x", actor="op@example.com",
                           verified="access")
        assert _plan()["hash"] != first, "another account signs in"

    def test_no_read_only_account_refuses_before_anything(self, lab, monkeypatch, capsys):
        monkeypatch.setattr(C, "_FILE", str(lab["dir"] / "other.json"))
        C.save_profile("default", username="netops", password=DEPLOY_PW)
        assert _main() == 1
        assert "REFUSED: no read-only account for edge1" in capsys.readouterr().out
        assert lab["opened"] == []


# ---------------------------------------------------------------------------- the confirm

class TestTheConfirm:
    def test_a_moved_program_is_refused_naming_both_hashes(self, lab, capsys):
        old = _plan()["hash"]
        lab["golden"] = GOLDEN + "interface GigabitEthernet2\n"
        new = _plan(interface="GigabitEthernet2")["hash"]
        lab["device"] = Device(lab["log"])
        assert _main("--interface", "GigabitEthernet2", "--confirm", old,
                     "--actor", "op@example.com") == 1
        out = capsys.readouterr().out
        assert f"--confirm {old}" in out and f"hash now, {new}" in out, out
        assert lab["opened"] == [] and lab["log"] == []

    def test_the_confirmed_hash_runs_and_is_recorded_with_its_actor(self, lab, capsys):
        lab["device"] = Device(lab["log"])
        h = _plan()["hash"]
        assert _main("--confirm", h, "--actor", "op@example.com") == 0
        (path,) = _records(lab)
        rec = json.loads(path.read_text())
        assert rec["actor"] == "op@example.com" and rec["hash"] == h
        assert rec["verdict"]["result"] == "PASS", rec["verdict"]
        assert oct(os.stat(path).st_mode & 0o777) == oct(0o600)

    def test_a_confirm_needs_a_person(self, lab, capsys):
        assert _main("--confirm", _plan()["hash"]) == 1
        assert "--actor" in capsys.readouterr().out and lab["opened"] == []

    def test_the_backup_window_refuses(self, lab, monkeypatch, capsys):
        """2026-11-13, under MST: 02:30 to 03:30 America/Denver is 09:30 to 10:30 UTC."""
        monkeypatch.setattr(_tool(), "in_backup_window", P._T2.in_backup_window)
        args = types.SimpleNamespace(network=NET, device=HOST, confirm="x", actor="op@x.invalid",
                                     **{k: "" for k in P.GIVEN})
        inside = calendar.timegm((2026, 11, 13, 9, 45, 0, 0, 0, 0))
        outside = calendar.timegm((2026, 11, 13, 10, 31, 0, 0, 0, 0))
        why = P.refusal(args, now=inside)
        assert "02:30 to 03:30 America/Denver (09:30 to 10:30 UTC on 2026-11-13)" in why, why
        assert P.refusal(args, now=outside) == ""
        monkeypatch.setattr(_tool(), "in_backup_window", lambda now=None: True)
        assert _main("--confirm", _plan()["hash"], "--actor", "op@example.com") == 1
        assert "backup window" in capsys.readouterr().out and lab["opened"] == []


# ---------------------------------------------------------------------------- the run

class TestTheRun:
    def test_a_privilege_1_device_passes_signed_in_as_the_account_held_throughout(self, lab):
        p, rec = _run(lab, Device(lab["log"]))
        assert rec["verdict"]["result"] == "PASS", rec["verdict"]
        params = lab["opened"][0]
        assert params["username"] == RO_NAME and params["password"] == RO_PW
        assert DEPLOY_PW not in params.values(), "nothing of the deploy login"
        assert ("enable", "") not in lab["log"], "never escalated"
        kinds = [k for k, _ in lab["log"]]
        assert kinds[0] == "hold" and kinds[1] == "open" and kinds[-1] == "release"
        assert kinds[-2] == "disconnect", "the session closed inside the hold"
        reads = [c for k, c in lab["log"] if k == "read"]
        assert reads == [r["command"] for r in p["reads"] if r.get("command")]
        assert all(r["result"] == "PASS" for r in rec["reads"]
                   if r.get("command")), rec["reads"]
        assert [r["result"] for r in rec["refused"]] == ["PASS"] * 4
        assert ("type", "debug ?") in lab["log"] and ("send", "debug ?") not in lab["log"]
        assert ("send", "end") not in lab["log"] and ("type", "n") not in lab["log"]

    def test_a_device_that_enters_configuration_mode_fails_and_is_sent_end(self, lab):
        device = Device(lab["log"], sends={"configure terminal": CONFIG_MODE,
                                           "end": END_ANSWER})
        _p, rec = _run(lab, device)
        row = {r["key"]: r for r in rec["refused"]}["configure-terminal"]
        assert row["result"] == "FAIL" and "the account can configure" in row["why"]
        i = lab["log"].index(("send", "configure terminal"))
        assert lab["log"][i + 1] == ("send", "end"), "end at once, before anything else"
        assert rec["verdict"]["result"] == "FAIL"
        assert {r["key"]: r for r in rec["refused"]}["clear-counters"]["result"] == "PASS"

    def test_a_confirm_is_answered_n_never_enter_and_fails(self, lab):
        """After `n`, the stand-in answers its prompt alone (not a capture)."""
        device = Device(lab["log"], sends={"clear counters": CONFIRM},
                        bare={"n": f"\n{HOST}#"})
        _p, rec = _run(lab, device)
        row = {r["key"]: r for r in rec["refused"]}["clear-counters"]
        assert row["result"] == "FAIL" and "[confirm]" in row["why"], row
        assert row["answered"] == "n"
        after = lab["log"][lab["log"].index(("send", "clear counters")) + 1]
        assert after == ("type", "n"), lab["log"]
        assert ("send", "\n") not in lab["log"] and ("send", "") not in lab["log"]
        assert ("type", "\n") not in lab["log"]
        assert rec["verdict"]["result"] == "FAIL"

    def test_debug_help_listing_fails(self, lab):
        """The listing is NOT a capture (none of `debug ?` exists in tests/fixtures): two lines
        in IOS's help form, then the line IOS types back."""
        listing = (f"debug ?\n  aaa              AAA Authentication, Authorization and "
                   f"Accounting\n  all              Enable all debugging\n\n{HOST}#debug ")
        _p, rec = _run(lab, Device(lab["log"], bare={"debug ?": listing}))
        row = {r["key"]: r for r in rec["refused"]}["debug-help"]
        assert row["result"] == "FAIL" and "answered, not refused" in row["why"], row
        assert rec["verdict"]["result"] == "FAIL"
        assert ("send", "debug ?") not in lab["log"], "never with Enter"

    @pytest.mark.parametrize("answer", ["", "% Ambiguous command:  \"sh\""])
    def test_an_unrecognised_answer_is_unreadable_never_pass(self, lab, answer):
        """The ambiguous line is one of `console_profiles.REFUSAL_EXAMPLES`: a `%` line that is
        not a refusal of the account."""
        device = Device(lab["log"], sends={"show running-config": answer},
                        reads={"show ip bgp summary": answer})
        _p, rec = _run(lab, device)
        row = {r["key"]: r for r in rec["refused"]}["show-running-config"]
        assert row["result"] == "UNREADABLE", row
        read = {r["op"]: r for r in rec["reads"]}["bgp_summary"]
        assert read["result"] == ("UNREADABLE" if answer else "PASS"), read
        assert rec["verdict"]["result"] == "UNREADABLE", rec["verdict"]

    def test_a_refused_read_fails_and_proposes_a_parser_view(self, lab):
        device = Device(lab["log"], reads={"show ip bgp summary": INVALID})
        _p, rec = _run(lab, device)
        read = {r["op"]: r for r in rec["reads"]}["bgp_summary"]
        assert read["result"] == "FAIL" and "Invalid input" in read["why"]
        v = rec["verdict"]
        assert v["result"] == "FAIL" and v["missed_reads"] == ["show ip bgp summary"]
        assert "parser view" in v["proposal"] and "never a wider privilege" in v["proposal"]

    def test_a_question_other_than_confirm_is_never_answered(self, lab):
        device = Device(lab["log"], sends={"clear counters": "Proceed? [yes/no]:"})
        _p, rec = _run(lab, device)
        row = {r["key"]: r for r in rec["refused"]}["clear-counters"]
        assert row["result"] == "FAIL" and rec["stopped"] == "clear-counters"
        assert {r["key"]: r for r in rec["refused"]}["debug-help"]["result"] == "not run"
        assert [k for k, _ in lab["log"]].count("type") == 0, "nothing typed after it"

    @pytest.mark.parametrize("line", [x for x in __import__(
        "modules.nsot.console_profiles", fromlist=["x"]).REFUSAL_EXAMPLES
        if x.startswith(("% Invalid", "% Incomplete", "% Unknown"))])
    def test_each_known_refusal_shape_is_refused(self, line):
        assert P.judge_refused(f"configure terminal\n{line}\n{HOST}>",
                               "configure terminal")["result"] == "PASS"


# ---------------------------------------------------------------------------- the password

class TestThePassword:
    def test_never_in_the_record_the_output_or_the_log(self, lab, capsys, caplog):
        caplog.set_level(logging.DEBUG)
        lab["device"] = Device(lab["log"], reads={"show ip bgp summary": f"echo {RO_PW}\n"})
        assert _main("--confirm", _plan()["hash"], "--actor", "op@example.com") == 0
        (path,) = _records(lab)
        text = path.read_text()
        assert RO_PW not in text and DEPLOY_PW not in text
        out = capsys.readouterr().out
        assert RO_PW not in out and DEPLOY_PW not in out
        assert RO_PW not in caplog.text and DEPLOY_PW not in caplog.text
        assert "the read-only account's password" in text, "masked, by its label"

    def test_a_sign_in_failure_is_its_own_verdict_naming_the_account(self, lab, capsys):
        from netmiko.exceptions import NetmikoAuthenticationException

        lab["device"] = NetmikoAuthenticationException(
            f"Authentication to device failed. (tried {RO_PW})")
        assert _main("--confirm", _plan()["hash"], "--actor", "op@example.com") == 2
        out = capsys.readouterr().out
        assert (f"the device does not accept the read-only account {RO_NAME} (profile default)"
                in out), out
        assert RO_PW not in out
        (path,) = _records(lab)
        rec = json.loads(path.read_text())
        assert rec["verdict"]["result"] == "SIGN-IN REFUSED" and RO_PW not in path.read_text()

    def test_a_timeout_is_no_verdict_about_the_account(self, lab):
        from netmiko.exceptions import NetmikoTimeoutException

        _p, rec = _run(lab, NetmikoTimeoutException("TCP connection to device failed."))
        assert rec["verdict"]["result"] == "UNREADABLE" and "no verdict" in rec["verdict"]["why"]
