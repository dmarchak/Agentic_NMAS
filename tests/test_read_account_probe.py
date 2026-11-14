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

`enable` (the operator, 2026-11-13: "plus `enable` refused"): accepted with nothing asked is a
capture (the console transcripts' own `enable`, tests/fixtures/console/); the `Password:` prompt
and `% No password set.` are NOT captures (tests/fixtures holds neither) and say so where they
are defined. The stand-in closes as Netmiko does (its `cleanup` types Enter and `exit`, logged),
so a test sees whatever a close types.

The probe's choices (the operator, 2026-11-13: "fix the probe's choices, not the account"):
CDP's and LLDP's interface is one committed intent gives a neighbour on, never a loopback (the
fixture's intent holds a second device on edge1's link), and spanning tree is not asked of a
device declared to have no VLAN database (Mercury's platform table's own C8000V entry).

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
    """``(module, script)``: the probe, `modules/read_account_probe.py`, its one home since
    board R's R8, and its command line at PATH, which runs the module's `main` with a refusal
    of its own (the lab's nightly backup window: lab tooling's, never the product's)."""
    spec = importlib.util.spec_from_file_location(
        "readaccountprobe", PATH, loader=SourceFileLoader("readaccountprobe", PATH))
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    mod = importlib.import_module("modules.read_account_probe")
    assert script._M is mod, "the script runs the module"
    return mod, script


_LOADED = []

#: The command line's own names (its refusal, `main`, the lab's backup window); every other
#: name is the module's.
SCRIPT_NAMES = ("refusal", "main", "in_backup_window", "_T2")


def _tool():
    """The probe, loaded once at first use, never at collection: each test is red, not the
    file, where the probe is absent (as tests/test_nmas_pregate.py loads its tool)."""
    if not _LOADED:
        _LOADED.append(_load())
    return _LOADED[0][0]


def _script():
    _tool()
    return _LOADED[0][1]


class _Probe:
    """The probe's names, read at each use (so a patch is seen): the command line's from the
    script, the rest from the module."""

    def __getattr__(self, name):
        return getattr(_script() if name in SCRIPT_NAMES else _tool(), name)


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


#: `enable`'s answer on a device with an enable secret: the echo, then the prompt for it. NOT
#: a capture (tests/fixtures holds no `Password:` prompt): IOS's own word, the one Netmiko's
#: `enable()` waits for (its pattern is `ssword`).
ENABLE_ASKS = "enable\nPassword: "
#: The device at the other end of edge1's GigabitEthernet1 in committed intent (the same IPv4
#: and IPv6 networks), so intent gives edge1 a neighbour on a cabled interface.
PEER = "edge2"
PEER_INTENT = {"platform": "cisco_iosxe",
               "interfaces": [{"name": "GigabitEthernet1", "ipv4": "192.0.2.22 255.255.255.0",
                               "ipv6": ["2001:db8::22/64"]}]}
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
        self.sends["enable"] = ENABLE_ASKS
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

    def cleanup(self, command="exit"):
        """Netmiko's own (`CiscoBaseConnection.cleanup`): Enter, to look for configuration
        mode, then `exit` and Enter. Whatever a close types is in the log."""
        self.log.append(("closing-type", "\n"))
        self.log.append(("closing-type", command + "\n"))

    def disconnect(self):
        """As Netmiko's `disconnect()`: its cleanup first, then the transport closed."""
        self.cleanup()
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
    state = {"intent": dict(INTENT), "golden": GOLDEN, "log": [], "opened": [], "device": None,
             "peer": dict(PEER_INTENT), "model": ""}
    # The inventory's row, its NetBox device type (`_model`) a test's to name: none by default.
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path: [dict(dev, _model=state["model"])])
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: types.SimpleNamespace(csv_path="unused", repo_dir="unused"))
    # Where the probe is absent (its commit's parent: no script, or a script whose module is not
    # there yet), nothing is patched: each test's own use of it then fails, so the test is red
    # rather than its setup. Only that import is caught; `_tool()` in the body raises it again.
    try:
        probe = _tool() if os.path.exists(PATH) else None
    except ImportError:
        probe = None
    if probe:
        monkeypatch.setattr(probe, "_committed", lambda network, host: (
            dict({HOST: state["intent"]}, **({PEER: state["peer"]} if state["peer"] else {})),
            {HOST: state["golden"]}))

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
        monkeypatch.setattr(_script(), "in_backup_window", lambda now=None: False)
        monkeypatch.setattr(probe, "no_change_now", lambda now=None: "")
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
        tail = [c for c in p["program"]][-5:]
        assert tail == ["show running-config", "configure terminal", "clear counters", "debug ?",
                        "enable"]

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
        # C3640: the device's connections, asked of the read-only account as the AI would ask
        # them; whether its level may run it is this probe's measurement (no line assumes it).
        assert sent["telemetry_connection"] == "show telemetry internal connection"
        assert sent["mac"] == f"show mac address-table address {MAC}"
        assert sent["ospfv3_neighbor"] == "show ospfv3 neighbor"
        # The lab's router is of no known VLAN database, so spanning tree, a switch's read, is
        # another platform's here (C3582).
        other = {r["op"]: r for r in p["reads"] if r.get("result") == "other platform"}
        assert list(other) == ["ipv6_ospf_neighbor", "stp"], other

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
        monkeypatch.setattr(_script(), "in_backup_window", P._T2.in_backup_window)
        args = types.SimpleNamespace(network=NET, device=HOST, confirm="x", actor="op@x.invalid",
                                     **{k: "" for k in P.GIVEN})
        inside = calendar.timegm((2026, 11, 13, 9, 45, 0, 0, 0, 0))
        outside = calendar.timegm((2026, 11, 13, 10, 31, 0, 0, 0, 0))
        why = P.refusal(args, now=inside)
        assert "02:30 to 03:30 America/Denver (09:30 to 10:30 UTC on 2026-11-13)" in why, why
        assert P.refusal(args, now=outside) == ""
        monkeypatch.setattr(_script(), "in_backup_window", lambda now=None: True)
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
        assert [r["result"] for r in rec["refused"]] == ["PASS"] * 5
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

    def test_a_protocol_that_is_not_running_is_an_answer_never_a_refusal(self, lab):
        """`% BGP not active`, whole and alone, as an IOS-XE router running no BGP answered both
        BGP summary reads at privilege 1 (the probe's record of 2026-11-13, the line as the
        record holds it): the read was accepted. It kept that run's verdict from PASS."""
        device = Device(lab["log"], reads={"show ip bgp summary": "% BGP not active",
                                           "show bgp ipv6 unicast summary": "% BGP not active"})
        _p, rec = _run(lab, device)
        rows = {r["op"]: r for r in rec["reads"]}
        for op in ("bgp_summary", "bgp_summary6"):
            assert rows[op]["result"] == "PASS", rows[op]
            assert "the protocol is not running" in rows[op]["why"]
        assert rec["verdict"]["result"] == "PASS", rec["verdict"]
        # Only that line, alone: beside anything else, or another `%` line, it decides nothing.
        for answer in ("% BGP not active\n% Invalid input detected at '^' marker.",
                       "% BGP not active here", "% OSPF not active", "x\n% BGP not active"):
            got = P.judge_read({"state": "answered", "command": "show ip bgp summary",
                                "answer": answer})
            assert got["result"] != "PASS", (answer, got)

    def test_a_refused_read_fails_and_proposes_privilege_exec_lines_never_a_parser_view(
            self, lab):
        """The operator, 2026-11-13: "NOT a parser view (it needs aaa new-model, an AAA change
        with lockout risk on every device). Propose a custom privilege level instead"."""
        device = Device(lab["log"], reads={"show ip bgp summary": INVALID})
        _p, rec = _run(lab, device)
        read = {r["op"]: r for r in rec["reads"]}["bgp_summary"]
        assert read["result"] == "FAIL" and "Invalid input" in read["why"]
        v = rec["verdict"]
        assert v["result"] == "FAIL" and v["missed_reads"] == ["show ip bgp summary"]
        assert "`privilege exec level <n> <command>` lines for exactly these" in v["proposal"]
        assert "never a parser view (it needs aaa new-model)" in v["proposal"]
        assert "never privilege 15" in v["proposal"]
        assert v["proposal"].endswith(": show ip bgp summary")

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


# ---------------------------------------------------------------------------- the choices

class TestTheProbesChoices:
    """The operator, 2026-11-13: three of r2's eleven refusals failed as the deploy account
    too ("probe shapes wrong for the platform or interface (spanning-tree on a router, CDP/LLDP
    on Loopback0): fix the probe's choices, not the account")."""

    LOOPBACK_FIRST = "interface Loopback0\n ip address 198.51.100.21 255.255.255.255\n" + GOLDEN

    def _with_loopback(self, lab):
        lab["golden"] = self.LOOPBACK_FIRST
        lab["intent"] = dict(INTENT, interfaces=[
            {"name": "Loopback0", "ipv4": "198.51.100.21 255.255.255.255",
             "ipv6": ["2001:db8:ff::21/128"]}] + INTENT["interfaces"])

    def test_cdp_and_lldp_ask_the_interface_intent_gives_a_neighbour_on_never_the_loopback(
            self, lab):
        """The golden's first interface is the loopback (as r2's is): every other interface
        read is asked of it, and CDP's and LLDP's of the link to edge2."""
        self._with_loopback(lab)
        sent = {r["op"]: r.get("command") for r in _plan()["reads"]}
        assert sent["interfaces"] == "show interfaces Loopback0"
        assert sent["cdp"] == "show cdp neighbors GigabitEthernet1 detail"
        assert sent["lldp"] == "show lldp neighbors GigabitEthernet1 detail"

    def test_a_device_intent_gives_no_neighbour_is_not_measured_and_says_why(self, lab):
        self._with_loopback(lab)
        lab["peer"] = None
        rows = {r["op"]: r for r in _plan()["reads"]}
        for op in ("cdp", "lldp"):
            assert rows[op]["result"] == P.NOT_MEASURED and "command" not in rows[op], rows[op]
            assert "no neighbour on a cabled interface" in rows[op]["why"]
            assert "--link-interface" in rows[op]["why"]
        assert rows["interfaces"]["command"] == "show interfaces Loopback0", "the others asked"

    def test_an_interface_no_cable_plugs_into_is_never_chosen(self, lab):
        """An SVI has a routing neighbour in intent and no cable: whether a device answers
        CDP's form for one is not measured, so the default is a cabled interface, and with
        only the SVI a neighbour's, the shape is NOT MEASURED."""
        svi = {"name": "Vlan10", "ipv4": "203.0.113.1 255.255.255.0",
               "ipv6": ["2001:db8:10::1/64"]}
        lab["golden"] = "interface Vlan10\n ip address 203.0.113.1 255.255.255.0\n" + GOLDEN
        lab["intent"] = dict(INTENT, interfaces=[svi] + INTENT["interfaces"])
        lab["peer"] = dict(PEER_INTENT, interfaces=PEER_INTENT["interfaces"] + [
            {"name": "Vlan10", "ipv4": "203.0.113.2 255.255.255.0"}])
        sent = {r["op"]: r.get("command") for r in _plan()["reads"]}
        assert sent["interfaces"] == "show interfaces Vlan10", "the golden's first"
        assert sent["cdp"] == "show cdp neighbors GigabitEthernet1 detail"
        lab["peer"] = dict(PEER_INTENT, interfaces=[
            {"name": "Vlan10", "ipv4": "203.0.113.2 255.255.255.0"}])
        rows = {r["op"]: r for r in _plan()["reads"]}
        assert rows["cdp"]["result"] == P.NOT_MEASURED and rows["lldp"]["result"] == P.NOT_MEASURED
        assert "no neighbour on a cabled interface" in rows["cdp"]["why"]

    def test_a_loopback_named_for_them_is_refused_by_the_ais_own_check(self, lab):
        self._with_loopback(lab)
        rows = {r["op"]: r for r in _plan(link_interface="Loopback0")["reads"]}
        for op in ("cdp", "lldp"):
            assert rows[op]["result"] == P.NOT_MEASURED, rows[op]
            assert "the AI's own check refuses it" in rows[op]["why"]
            assert "Loopback0 is a loopback" in rows[op]["why"]

    def test_the_link_interface_is_an_argument_of_the_command_line(self, lab, capsys):
        lab["golden"] = GOLDEN + "interface GigabitEthernet2\n"
        assert _main("--link-interface", "GigabitEthernet2") == 0
        out = capsys.readouterr().out
        assert "show cdp neighbors GigabitEthernet2 detail" in out
        assert "show interfaces GigabitEthernet1" in out, "the other reads keep the first"

    def test_spanning_tree_is_another_platforms_form_where_no_vlan_database_is_declared(
            self, lab):
        """Mercury's platform table declares the C8000V has no VLAN database
        (modules/nsot/platform_capabilities.json): spanning tree, a switch's read, is not
        asked of it, as the other dialect's OSPFv3 form is not."""
        lab["model"] = "C8000V"
        p = _plan()
        other = {r["op"]: r for r in p["reads"] if r.get("result") == "other platform"}
        assert list(other) == ["ipv6_ospf_neighbor", "stp"], other
        assert "has no VLAN database" in other["stp"]["why"]
        assert "this form is a switch's" in other["stp"]["why"]
        assert not [c for c in p["program"] if "spanning-tree" in c]

    def test_the_connections_are_another_platforms_form_on_ios(self, lab):
        """C3640: `show telemetry internal connection` is IOS-XE's, never asked of IOS, as the
        AI's check refuses it there (`router_reads.other_platform`, one comparison)."""
        lab["intent"] = dict(INTENT, platform="cisco_ios")
        p = _plan()
        other = {r["op"]: r for r in p["reads"] if r.get("result") == "other platform"}
        assert "telemetry_connection" in other and "ospfv3_neighbor" in other, other
        assert other["telemetry_connection"]["why"] == (
            f"{HOST}'s platform is cisco_ios, and this form is cisco_iosxe's")
        assert "show telemetry internal connection" not in p["program"]

    def test_spanning_tree_is_not_asked_where_nothing_says_the_device_is_a_switch(self, lab):
        """Not declared and not measured is unknown, and spanning tree is asked only of a
        switch (the operator, 2026-11-14: "spanning-tree only on switches. Fix both, so they
        agree"; C3582: every router on the host was unknown, so r7 was asked it again)."""
        p = _plan()
        other = {r["op"]: r for r in p["reads"] if r.get("result") == "other platform"}
        assert "stp" in other, other
        assert "is not known to have a VLAN database" in other["stp"]["why"]
        assert "asked only of a device known to be one" in other["stp"]["why"]
        assert not [c for c in p["program"] if "spanning-tree" in c]

    def test_spanning_tree_is_asked_of_a_device_measured_a_switch(self, lab, monkeypatch):
        monkeypatch.setattr("modules.ai.router_reads.vlan_databases", lambda network, hosts: {
            h: (True, "measured: a VLAN database (a test's own words)") for h in hosts})
        p = _plan()
        assert "show spanning-tree interface GigabitEthernet1" in p["program"]

    def test_another_platforms_form_keeps_no_verdict_from_pass(self, lab):
        lab["model"] = "C8000V"
        _p, rec = _run(lab, Device(lab["log"]))
        assert rec["verdict"]["result"] == "PASS", rec["verdict"]
        assert ("read", "show spanning-tree interface GigabitEthernet1") not in lab["log"]


# ---------------------------------------------------------------------------- enable

def _refused_row(rec, key="enable"):
    return {r["key"]: r for r in rec["refused"]}[key]


class TestEnableIsRefused:
    """The operator, 2026-11-13: "Re-probe after: reads answer; the four stay refused, plus
    `enable` refused"."""

    def test_a_password_prompt_is_never_answered_and_counts_as_refused(self, lab):
        _p, rec = _run(lab, Device(lab["log"]))
        row = _refused_row(rec)
        assert row["result"] == "PASS" and "never answered" in row["why"], row
        i = lab["log"].index(("send", "enable"))
        after = [k for k, _ in lab["log"][i + 1:]]
        assert after == ["disconnect", "release"], lab["log"][i:]
        assert ("enable", "") not in lab["log"], "Netmiko's enable() is never called"
        assert RO_PW not in json.dumps(rec) and DEPLOY_PW not in json.dumps(rec)

    def test_it_runs_in_a_session_of_its_own_after_the_debug_step_s_is_closed(self, lab):
        _p, _rec = _run(lab, Device(lab["log"]))
        kinds = [(k, c) for k, c in lab["log"] if k in ("open", "disconnect", "type", "send")]
        i = kinds.index(("type", "debug ?"))
        assert [k for k, _ in kinds[i + 1:i + 4]] == ["disconnect", "open", "send"], kinds[i:]
        assert kinds[i + 3] == ("send", "enable")
        assert len(lab["opened"]) == 2 and all(o["username"] == RO_NAME for o in lab["opened"])

    def test_no_close_types_anything(self, lab):
        """Netmiko's close types Enter and `exit` (the stand-in's `cleanup`, as Netmiko's):
        at a `Password:` prompt that is an answer, and after `debug ?` it sends the line left
        behind. Every session of the probe is closed with nothing typed."""
        _p, _rec = _run(lab, Device(lab["log"]))
        assert [e for e in lab["log"] if e[0] == "closing-type"] == [], lab["log"]
        assert [k for k, _ in lab["log"]].count("disconnect") == 2

    def test_a_question_left_unanswered_is_closed_with_nothing_typed(self, lab):
        device = Device(lab["log"], sends={"clear counters": "Proceed? [yes/no]:"})
        _p, rec = _run(lab, device)
        assert rec["stopped"] == "clear-counters"
        assert [e for e in lab["log"] if e[0] == "closing-type"] == [], lab["log"]
        assert _refused_row(rec)["result"] == "not run"

    def test_accepted_with_nothing_asked_fails(self, lab):
        """As captured on a console with no enable secret (tests/fixtures/console/): the echo,
        then the privileged prompt."""
        accepted = _console("enable")
        assert accepted.strip().splitlines() == ["enable", "Switch#"], accepted
        _p, rec = _run(lab, Device(lab["log"], sends={"enable": accepted}))
        row = _refused_row(rec)
        assert row["result"] == "FAIL" and "accepted with no password asked" in row["why"], row
        assert rec["verdict"]["result"] == "FAIL"
        assert lab["log"][lab["log"].index(("send", "enable")) + 1] == ("disconnect", "")

    def test_a_device_error_is_refused_whatever_the_prompt_after_it(self, lab):
        """`% No password set.` is NOT a capture (tests/fixtures holds none): IOS's line for
        `enable` on a vty line of a device with no enable secret. A custom level's prompt is
        `#` already, so the prompt after the error decides nothing."""
        for prompt in (f"{HOST}>", f"{HOST}#"):
            got = P.judge_enable(f"enable\n% No password set.\n{prompt}")
            assert got["result"] == "PASS" and "% No password set." in got["why"], got

    @pytest.mark.parametrize("answer", ["", f"enable\n{HOST}>", "enable\nUsername: ",
                                        "enable\nsomething else\nedge1#"])
    def test_anything_else_is_unreadable_never_pass(self, lab, answer):
        _p, rec = _run(lab, Device(lab["log"], sends={"enable": answer}))
        assert _refused_row(rec)["result"] == "UNREADABLE", _refused_row(rec)
        assert rec["verdict"]["result"] == "UNREADABLE"

    def test_a_password_prompt_on_a_custom_levels_own_prompt_is_refused(self):
        """At a level above 1 the session's prompt is `#` before `enable`: the password
        prompt, not the prompt before it, is what says refused."""
        assert P.judge_enable(f"{HOST}#enable\nPassword: ")["result"] == "PASS"

    def test_the_hash_declares_what_is_never_answered(self, lab, monkeypatch):
        first = _plan()["hash"]
        monkeypatch.setattr(_tool(), "NEVER_ANSWERED", [])
        assert _plan()["hash"] != first

    def test_a_session_that_cannot_be_opened_again_is_no_verdict(self, lab, monkeypatch):
        from netmiko.exceptions import NetmikoTimeoutException

        device = Device(lab["log"])
        p = _plan()
        opens = []

        def opener(params):
            opens.append(params["username"])
            if len(opens) > 1:
                raise NetmikoTimeoutException("TCP connection to device failed.")
            return device

        monkeypatch.setattr(_tool(), "OPEN", opener)
        rec = P.run(p, P._inventory(NET)[HOST], "op@example.com", {}, 32 * 1024)
        row = _refused_row(rec)
        assert row["result"] == "UNREADABLE" and "could not be opened" in row["why"], row
        assert rec["verdict"]["result"] == "UNREADABLE"


# ---------------------------------------------------------------------------- the choice

class TestPingAndTracerouteByTheInstallationChoice:
    """The operator, 2026-11-13: "Ping and traceroute: not by default. An installation choice
    `Let the read-only account ping and traceroute`, off by default". Off, the AI's ping is
    the plain form (its 5 echoes and 2 seconds are the device's defaults) and its sourced ping
    and its traceroute are refused by name, so the probe does not ask them of the account."""

    CHOICE = ("ping_from", "ping6_from", "traceroute", "traceroute6")

    def test_off_the_plain_pings_are_asked_and_the_forms_with_options_are_not(self, lab):
        p = _plan()
        rows = {r["op"]: r for r in p["reads"]}
        assert rows["ping"]["command"] == "ping 192.0.2.21"
        assert rows["ping6"]["command"] == "ping ipv6 2001:db8::21", "IPv6 beside IPv4"
        for op in self.CHOICE:
            assert rows[op]["result"] == P.NOT_ASKED and "command" not in rows[op], rows[op]
            assert ("it needs the installation choice \"Let the read-only account ping and "
                    "traceroute\" (ai_read_account_ping_traceroute is off)") in rows[op]["why"]
        assert not [c for c in p["program"] if c.startswith("traceroute") or " source " in c
                    or " repeat " in c], p["program"]

    def test_off_they_are_listed_in_the_preview_and_keep_no_verdict_from_pass(
            self, lab, capsys):
        assert _main() == 0
        out = capsys.readouterr().out
        assert "Not asked (the AI's own check refuses it by name):" in out
        assert out.count("it needs the installation choice") == 4
        _p, rec = _run(lab, Device(lab["log"]))
        assert rec["verdict"]["result"] == "PASS", rec["verdict"]
        kept = {r["op"]: r for r in rec["reads"]}
        assert all(kept[op]["result"] == P.NOT_ASKED for op in self.CHOICE), "in the record"
        assert not [c for k, c in lab["log"] if k == "read" and c.startswith("traceroute")]

    def test_on_they_are_asked_as_the_ai_would_ask_them(self, lab, monkeypatch):
        off = _plan()["hash"]
        monkeypatch.setattr("modules.ai.router_reads.ping_traceroute_on", lambda: True)
        p = _plan()
        sent = {r["op"]: r.get("command") for r in p["reads"]}
        assert sent["ping"] == "ping 192.0.2.21", "the plain ping either way"
        assert sent["ping_from"] == "ping 192.0.2.21 source GigabitEthernet1 repeat 5 timeout 2"
        assert sent["ping6_from"] == ("ping ipv6 2001:db8::21 source GigabitEthernet1 repeat 5 "
                                      "timeout 2")
        assert sent["traceroute"] == "traceroute 192.0.2.21 numeric timeout 2 probe 1 ttl 1 16"
        assert sent["traceroute6"] == ("traceroute ipv6 2001:db8::21 numeric timeout 2 probe 1 "
                                       "ttl 1 16")
        assert not [r for r in p["reads"] if r.get("result") == P.NOT_ASKED]
        assert p["hash"] != off, "the choice moves the program, so its hash"

    def test_a_form_not_asked_is_no_part_of_the_verdict_and_a_refused_one_still_fails(
            self, lab, monkeypatch):
        """With the choice on, a device whose level lacks the lines refuses the form: FAIL."""
        monkeypatch.setattr("modules.ai.router_reads.ping_traceroute_on", lambda: True)
        cmd = "traceroute 192.0.2.21 numeric timeout 2 probe 1 ttl 1 16"
        _p, rec = _run(lab, Device(lab["log"], reads={cmd: INVALID}))
        assert rec["verdict"]["result"] == "FAIL" and cmd in rec["verdict"]["missed_reads"]
