"""The revert-timer probe (scripts/nmas-revert-probe; C2458, for C2424 and C2425;
docs/HEAL_TO_INTENT.md 19.4, guard 13f and "The operator's step").

The probe MEASURES what IOS and IOS-XE do with ``configure terminal revert timer`` and
``configure confirm``, so its tests hold its reading, deciding, refusing and repairing, never a
claim about the devices. The device is faked at the probe's seams (``_session`` and
``modules.commands.run_device_command``), as tests/test_tier2_probe.py fakes it. The fake's
answers are INPUTS to the probe's parser, modelled on the command reference (an unknown command
is ``% Invalid input``, ``configure confirm`` with nothing pending is refused, a revert timer
without an archive is refused); the probe exists to measure the real ones. The running
configuration and the IPv4 interface brief are real captures (r3, tests/fixtures/), and the CEF
answers are the shapes captured in tests/fixtures/path/cef_fleet.json.
"""

import calendar
import importlib.util
import json
import os
import re
import threading
import types
from importlib.machinery import SourceFileLoader

import pytest

from modules.nsot import device_ops as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "scripts", "nmas-revert-probe")


def _load():
    loader = SourceFileLoader("revertprobe", PATH)
    spec = importlib.util.spec_from_file_location("revertprobe", PATH, loader=loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


P = _load()


def _cap(*parts):
    with open(os.path.join(ROOT, "tests", "fixtures", *parts), encoding="utf-8") as fh:
        return fh.read()


R3 = _cap("configs", "fleet", "r3.cfg")
BRIEF = _cap("operational", "r3__show_ip_interface_brief.txt")
MGMT_IF, MGMT_IP = BRIEF.splitlines()[1].split()[:2]          # GigabitEthernet1 and its address
#: IPv6: r3's own Gi4 address (r3.cfg), the brief in IOS's IPv6 form.
V6_BRIEF = ("GigabitEthernet1       [up/up]\n    FE80::5054:FF:FE00:1\n"
            "GigabitEthernet4       [up/up]\n    FE80::5054:FF:FE00:4\n    2001:DB8:2:E::1\n")
MANAGER = "192.0.2.250"
MANAGER_V6 = "2001:DB8:FFFF::250"
CEF_VIA_MGMT = f"0.0.0.0/0\n  nexthop 192.0.2.1 {MGMT_IF}"
CEF_VIA_GI4 = "192.0.2.0/24\n  nexthop 192.0.2.41 GigabitEthernet4\n  nexthop 192.0.2.42 GigabitEthernet3"
SAVE = re.compile(r"^\s*(?:do\s+)?(?:wr|write|copy\s+\S*run)", re.I)
T0 = calendar.timegm((2026, 11, 4, 14, 0, 0, 0, 0, 0))


class Clock:
    def __init__(self, now=T0):
        self.now = float(now)

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s


class FakeIOS:
    """One device: its running configuration, ports, revert timer and log, shared by every
    session the probe opens. ``unit_word`` is how its timer read states the unit (None: it
    states none); ``refuse`` lines answer ``% Incomplete command.`` (``refuse_once`` only the
    first time); ``drop_after`` is the last line of a batch the device receives; ``unreachable``
    are ``(from, to)`` seconds after T0 when no session opens."""

    def __init__(self, clock, *, archive=True, unit_word="minutes", up_delay=3.0,
                 cef=CEF_VIA_MGMT, manager=MANAGER, unreachable=(), drop_after="",
                 lose_batch_session=False, refuse=(), refuse_once=(), config=R3):
        self.clock, self.archive, self.unit_word, self.up_delay = clock, archive, unit_word, up_delay
        self.cef, self.manager, self.unreachable = cef, manager, unreachable
        self.drop_after, self.lose_batch_session = drop_after, lose_batch_session
        self.refuse, self.refuse_once = set(refuse), set(refuse_once)
        self.config = config
        self.ifaces = [ln.split(None, 1)[1].strip() for ln in config.splitlines()
                       if ln.startswith("interface ")]
        self.shut, self.up_at, self.pending = set(), {}, None
        self.log = ["*Nov  4 13:59:01.001 UTC: %SYS-5-CONFIG_I: Configured from console by op"]
        self.sent, self.batches, self.saves, self.opened = [], [], [], 0
        self.on_open = None

    # ------------------------------------------------------------- state
    def tick(self):
        if self.pending and self.clock.now >= self.pending["expires"]:
            for name in self.shut - self.pending["shut"]:
                self.up_at[name] = self.clock.now + self.up_delay
            self.shut = set(self.pending["shut"])
            self.log.append("*Nov  4 14:01:00.000 UTC: %ARCHIVE_DIFF-5-ROLLBK_CNFMD_CHG_ROLLBACK"
                            "_START: Timer expired: rolling back to bootflash:/nmas-archive-1")
            self.pending = None

    def running(self):
        out = []
        for line in self.config.splitlines():
            out.append(line)
            if line.startswith("interface ") and line.split(None, 1)[1].strip() in self.shut:
                out.append(" shutdown")
        return "\n".join(out) + "\n"

    def open(self):
        self.tick()
        t = self.clock.now - T0
        if self.on_open:
            self.on_open()
        if any(a <= t < b for a, b in self.unreachable):
            raise OSError("TCP connection to device failed")
        self.opened += 1
        return Conn(self)

    def show(self, cmd):
        self.tick()
        now = self.clock.now
        if cmd == "show running-config":
            return self.running()
        if cmd.startswith("show interfaces "):
            name = cmd.split(None, 2)[2]
            if name not in self.ifaces:
                return "                 ^\n% Invalid input detected at '^' marker.\n"
            if name in self.shut:
                return f"{name} is administratively down, line protocol is down \n  Hardware is vNIC"
            up = now >= self.up_at.get(name, 0)
            word = "up" if up else "down"
            return f"{name} is {word}, line protocol is {word} \n  Hardware is vNIC"
        if cmd == "show logging":
            return "Syslog logging: enabled\n\nLog Buffer (8192 bytes):\n" + "\n".join(self.log)
        if cmd == P.ROLLBACK_READ:
            if not self.pending:
                return "%No Rollback Confirmed Change pending\n"
            unit = f" {self.unit_word}" if self.unit_word else ""
            return ("Time configured(or reset) : 14:00:00 UTC Wed Nov 4 2026\n"
                    "Timer type     : absolute\n"
                    f"Timer value    : {self.pending['n']}{unit}\nUser           : op\n")
        if cmd == "show ip interface brief":
            return BRIEF
        if cmd == "show ipv6 interface brief":
            return V6_BRIEF
        if cmd.startswith("show ip cef ") or cmd.startswith("show ipv6 cef "):
            return self.cef
        return "% Invalid input detected at '^' marker.\n"

    def batch(self, text):
        self.tick()
        lines = text.split("\n")
        self.batches.append(lines)
        out, mode, cur = [], "exec", ""
        for line in lines:
            self.sent.append(line)
            s = line.strip()
            if SAVE.match(s):
                self.saves.append(s)
            if s in self.refuse or s in self.refuse_once:
                self.refuse_once.discard(s)
                out.append("% Incomplete command.")
            elif mode == "exec" and s.startswith("configure terminal revert timer "):
                if not self.archive:
                    out.append("% Rollback Confirmed Change needs an archive path configured")
                else:
                    n = int(s.split()[-1])
                    secs = 1 if (self.unit_word or "").startswith("sec") else 60
                    self.pending = {"expires": self.clock.now + n * secs, "n": n,
                                    "shut": set(self.shut)}
                    self.log.append("*Nov  4 14:00:00.000 UTC: %ARCHIVE_DIFF-5-ROLLBK_CNFMD_CHG_"
                                    "START_ABSTIMER: Scheduled to rollback to bootflash:/nmas-"
                                    "archive-1")
                    out.append("Rollback Confirmed Change: Backing up current running config "
                               "to bootflash:/nmas-archive-1")
                    mode = "config"
            elif mode == "exec" and s == "configure terminal":
                mode = "config"
            elif mode == "exec" and s == "configure confirm":
                if not self.pending:
                    out.append("%No Rollback Confirmed Change pending")
                else:
                    self.pending = None
                    self.log.append("*Nov  4 14:00:30.000 UTC: %ARCHIVE_DIFF-5-ROLLBK_CNFMD_CHG_"
                                    "CONFIRM: Confirm the configuration change")
            elif mode in ("config", "if") and s.startswith("interface "):
                name = s.split(None, 1)[1]
                if name in self.ifaces:
                    mode, cur = "if", name
                else:
                    out.append("% Invalid input detected at '^' marker.")
            elif mode == "if" and s == "shutdown":
                self.shut.add(cur)
            elif mode == "if" and s == "no shutdown":
                self.shut.discard(cur)
                self.up_at[cur] = self.clock.now + self.up_delay
            elif mode != "exec" and s == "end":
                mode = "exec"
            else:
                out.append("% Invalid input detected at '^' marker.")
            if self.drop_after and s == self.drop_after:
                break
        if self.lose_batch_session:
            self.lose_batch_session = False
            raise OSError("Socket is closed")
        return "\n".join(out + ["r3#"])


class Conn:
    def __init__(self, dev):
        self.device = dev
        sock = types.SimpleNamespace(getsockname=lambda: (dev.manager, 51515))
        self.remote_conn = types.SimpleNamespace(
            get_transport=lambda: types.SimpleNamespace(sock=sock))

    def send_command_timing(self, text, **kw):
        return self.device.batch(text)

    def disconnect(self):
        pass


@pytest.fixture(autouse=True)
def no_hold_survives_a_test():
    yield
    with D._mu:
        stale = list(D._held.items())
        D._held.clear()
    for _key, info in stale:
        if info["fd"] is not None:
            os.close(info["fd"])


@pytest.fixture
def lab(monkeypatch, tmp_path):
    clock = Clock()
    # The bounce's planned window (C2702) is recorded in this test's own folder (C1864).
    monkeypatch.setattr("modules.restarts._data", lambda name: str(tmp_path / name))
    # Committed intent with the bounced link's far end (C2749: the window covers it too).
    monkeypatch.setattr(P, "_intents", lambda l: (LINK, ""))
    monkeypatch.setattr(P, "CLOCK", clock.time)
    monkeypatch.setattr(P, "SLEEP", clock.sleep)
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, cmd, **kw: conn.device.show(cmd))
    state = types.SimpleNamespace(clock=clock, dev=None)

    def make(**kw):
        state.dev = FakeIOS(clock, **kw)
        monkeypatch.setattr(P, "_session", lambda device: state.dev.open())
        return state.dev

    state.make = make
    return state


def _args(**kw):
    base = {"list_name": "Lab", "device": "r3", "actor": "op@example.invalid", "apply": True,
            "interface": "GigabitEthernet4", "timer": 1, "path": "revert", "out": "/nonexistent"}
    return types.SimpleNamespace(**{**base, **kw})


DEVICE = {"hostname": "r3", "ip": MGMT_IP, "device_type": "cisco_xe"}

#: The r3 to r4 link in committed intent, both families (r4 the far end of r3's Gi4).
LINK = {"r3": {"interfaces": [{"name": "GigabitEthernet4", "ipv4": "192.0.2.13 255.255.255.252",
                               "ipv6": ["2001:DB8:34::3/64"]}]},
        "r4": {"interfaces": [{"name": "GigabitEthernet4", "ipv4": "192.0.2.14 255.255.255.252",
                               "ipv6": ["2001:DB8:34::4/64"]}]}}


def _run(lab, device=DEVICE, **kw):
    return P.run(_args(**kw), dict(device), {})


# ---------------------------------------------------------------------------- the program

class TestDryRun:
    def test_it_sends_nothing_and_prints_the_program_and_its_hash(self, monkeypatch, capsys):
        monkeypatch.setattr(P, "_session", lambda d: pytest.fail("a dry run connected"))
        monkeypatch.setattr("sys.argv", ["nmas-revert-probe", "--interface", "GigabitEthernet4",
                                         "--timer", "2", "--path", "confirm"])
        assert P.main() == 0
        out = capsys.readouterr().out
        assert out.startswith("DRY RUN: nothing connects and nothing is sent")
        prog = ["configure terminal revert timer 2", "interface GigabitEthernet4", "shutdown",
                "no shutdown", "end"]
        assert P.program("GigabitEthernet4", 2) == prog
        for line in prog:
            assert f"  {line}\n" in out
        from modules.nsot.deploy import command_fingerprint
        want = command_fingerprint(prog, [{"line": "shutdown", "reason": P.AUTH_REASON}])
        assert f"hash: {want} (modules.nsot.deploy.command_fingerprint" in out

    def test_the_hash_moves_with_the_program(self):
        assert P.program_hash(P.program("GigabitEthernet4", 1)) != \
            P.program_hash(P.program("GigabitEthernet4", 2))
        assert P.program_hash(P.program("GigabitEthernet4", 1)) != \
            P.program_hash(P.program("GigabitEthernet3", 1))

    @pytest.mark.parametrize("kw, words", [
        ({"interface": "Gi4;reload"}, "is not one interface name"),
        ({"interface": ""}, "is not one interface name"),
        ({"timer": 0}, "is not a whole number of at least 1"),
        ({"path": "both"}, "is not one of revert, confirm"),
        ({"actor": ""}, "needs --list, --device, --actor")])
    def test_an_argument_out_of_shape(self, kw, words):
        assert words in P.refusal(_args(**kw), now=T0)


# ---------------------------------------------------------------------------- reading

class TestReading:
    @pytest.mark.parametrize("text, admin, up_up", [
        ("GigabitEthernet4 is up, line protocol is up \n  Hardware", "up", True),
        ("GigabitEthernet4 is administratively down, line protocol is down ", "down", False),
        ("GigabitEthernet4 is down, line protocol is down ", "up", False)])
    def test_a_port_state(self, text, admin, up_up):
        got = P.port_state(text)
        assert (got["admin"], got["up_up"], got["unknown"]) == (admin, up_up, False)

    def test_an_answer_that_is_no_port_state_is_unknown(self):
        assert P.port_state("% Invalid input detected at '^' marker.")["unknown"]

    @pytest.mark.parametrize("text, err", [
        ("% Invalid input detected at '^' marker.", True), ("% Incomplete command.", True),
        ("% Ambiguous command:  \"sh\"", True), ("%No Rollback Confirmed Change pending", True),
        ("*Nov  4: %ARCHIVE_DIFF-5-ROLLBK_CNFMD_CHG_CONFIRM: Confirm", False),
        ("%ARCHIVE_DIFF-5-ROLLBK_CNFMD_CHG_START_ABSTIMER: Scheduled", False),
        ("Rollback Confirmed Change: Backing up", False)])
    def test_a_device_error(self, text, err):
        assert bool(P.device_errors(text)) is err

    @pytest.mark.parametrize("text, word, seconds", [
        ("Timer value    : 1 minutes", "minutes", 60), ("in 90 seconds", "seconds", 1),
        ("Timer value: 2 min", "min", 60)])
    def test_the_unit_as_the_device_states_it(self, text, word, seconds):
        assert P.stated_unit(text) == {"n": int(re.search(r"\d+", text).group()), "word": word,
                                       "seconds": seconds}

    def test_no_unit_stated_is_none_never_assumed(self):
        assert P.stated_unit("Timer value    : 1") is None

    def test_the_archive_path_in_intent(self):
        assert P.archive_path({"archive": {"path": "bootflash:nmas-archive"}}) == \
            "bootflash:nmas-archive"
        assert P.archive_path({"unmodeled": [{"line": "archive",
                                              "children": [" path bootflash:a", " maximum 3"]}]}) \
            == "bootflash:a"
        assert P.archive_path({"unmodeled": [{"line": "archive", "children": [" maximum 3"]}]}) == ""
        assert P.archive_path({}) == ""

    def test_the_management_interface_ipv4_and_ipv6(self):
        assert P.interface_with_address(BRIEF, MGMT_IP) == MGMT_IF
        assert P.interface_with_address(V6_BRIEF, "2001:db8:2:e::1") == "GigabitEthernet4"
        assert P.interface_with_address(BRIEF, "192.0.2.99") == ""

    @pytest.mark.parametrize("text, egress", [
        (CEF_VIA_GI4, {"GigabitEthernet4", "GigabitEthernet3"}),
        ("192.0.2.250/32\n  attached to GigabitEthernet2", {"GigabitEthernet2"}),
        ("2001:DB8:FFFF::/48\n  nexthop FE80::5054:FF:FE00:4 GigabitEthernet4",
         {"GigabitEthernet4"}),
        ("0.0.0.0/0\n  no route", set()), ("% Invalid input detected at '^' marker.", set())])
    def test_cef_egress_both_families(self, text, egress):
        assert P.egress_interfaces(text)[0] == egress


# ---------------------------------------------------------------------------- refused first

class TestRefusedBeforeSending:
    def test_the_lab_declares_s3_never_probed(self, lab):
        with open(P.NEVER_PROBE, encoding="utf-8") as fh:
            assert "s3" in json.load(fh)["devices"]
        why = P.refusal(_args(device="s3"), now=T0)
        assert "--device s3 is declared never-probe in lab/never-probe.json" in why
        assert "C93" in why and "compared it with the declared devices (s3)" in why
        assert P.refusal(_args(device="r3"), now=T0) == ""

    def test_an_absent_declaration_refuses(self, tmp_path):
        why = P.never_probe("r3", str(tmp_path / "never-probe.json"))
        assert why.startswith("REFUSED: the lab's never-probe declaration") and "absent" in why

    @pytest.mark.parametrize("h, m, refused", [(8, 30, False), (9, 25, False), (9, 27, True),
                                               (9, 45, True), (10, 29, True), (10, 30, False),
                                               (12, 0, False)])
    def test_the_backup_window_over_the_whole_run(self, h, m, refused):
        """A one-minute timer and the watch run four minutes: started 09:27, it ends inside.
        2026-11-04 is under MST, so the window (02:30 to 03:30 America/Denver) is 09:30 to 10:30
        UTC and 08:30 UTC is outside it (C2613)."""
        now = calendar.timegm((2026, 11, 4, h, m, 0, 0, 0, 0))
        why = P.refusal(_args(), now=now)
        assert ("overlaps the hypervisor's nightly backup window, 02:30 to 03:30 America/Denver "
                "(09:30 to 10:30 UTC on 2026-11-04)" in why) is refused
        if refused:
            assert f"{h:02d}:{m:02d} to" in why

    def test_main_refuses_s3_and_the_window_before_connecting(self, lab, monkeypatch, capsys):
        dev = lab.make()
        monkeypatch.setattr(P, "_device", lambda *a: pytest.fail("looked the device up"))

        def argv(device):
            return ["nmas-revert-probe", "--list", "Lab", "--device", device, "--interface",
                    "GigabitEthernet4", "--timer", "1", "--apply", "--actor",
                    "op@example.invalid", "--out", "/nonexistent"]

        monkeypatch.setattr("sys.argv", argv("s3"))
        assert P.main() == 1
        assert "declared never-probe" in capsys.readouterr().out
        lab.clock.now = calendar.timegm((2026, 11, 4, 9, 40, 0, 0, 0, 0))
        monkeypatch.setattr("sys.argv", argv("r3"))
        assert P.main() == 1
        assert "backup window" in capsys.readouterr().out
        assert dev.opened == 0 and dev.sent == []

    def test_no_archive_in_intent_is_refused_naming_the_field(self):
        why = P.intent_refusal("r3", "Lab", {"r3": {"interfaces": []}})
        assert "r3 has no configuration archive in its intent" in why
        assert "(host_vars, `archive.path`)" in why and "committed host_vars/r3.yml" in why
        assert P.intent_refusal("r3", "Lab", {"r3": {"archive": {"path": "bootflash:a"}}}) == ""
        assert "no committed intent" in P.intent_refusal("r3", "Lab", {})

    def test_main_refuses_no_archive_before_connecting(self, lab, monkeypatch, capsys):
        dev = lab.make()
        monkeypatch.setattr(P, "_device", lambda *a: dict(DEVICE))
        monkeypatch.setattr(P, "_intents", lambda l: ({"r3": {"interfaces": []}}, ""))
        monkeypatch.setattr(P, "_host_networks", lambda: ["192.0.2.0/24"])
        monkeypatch.setattr("sys.argv", ["nmas-revert-probe", "--list", "Lab", "--device", "r3",
                                         "--interface", "GigabitEthernet4", "--timer", "1",
                                         "--apply", "--actor", "op@example.invalid", "--out",
                                         "/nonexistent"])
        assert P.main() == 1
        assert "no configuration archive in its intent" in capsys.readouterr().out
        assert dev.opened == 0 and dev.sent == []

    INTENTS = {"edge1": {"archive": {"path": "bootflash:a"}, "interfaces": [
                   {"name": "GigabitEthernet1", "ipv4": "192.0.2.21 255.255.255.128"},
                   {"name": "GigabitEthernet4", "ipv4": "192.0.2.200 255.255.255.254"}]},
               "edge2": {"interfaces": [
                   {"name": "GigabitEthernet1", "ipv4": "192.0.2.201 255.255.255.254"}]}}

    def test_the_only_path_is_refused_by_the_blast_radius(self):
        why = P.radius_refusal(self.INTENTS, ["192.0.2.0/25"], "edge1", "GigabitEthernet4")
        assert "GigabitEthernet4 is edge1's only path: shutting it leaves edge2 unreachable" in why
        assert "192.0.2.0/25" in why
        both = json.loads(json.dumps(self.INTENTS))
        both["edge2"]["interfaces"].append({"name": "GigabitEthernet2",
                                            "ipv4": "192.0.2.22 255.255.255.128"})
        assert P.radius_refusal(both, ["192.0.2.0/25"], "edge1", "GigabitEthernet4") == ""
        assert "is not known" in P.radius_refusal(self.INTENTS, ["192.0.2.128/27"], "edge1",
                                                  "GigabitEthernet4")

    def test_the_management_interface_is_refused_ipv4(self, lab):
        dev = lab.make()
        rec = _run(lab, interface=MGMT_IF)
        assert f"{MGMT_IF} carries r3's management address {MGMT_IP}" in rec["refused"]
        assert "`show ip interface brief` on r3" in rec["refused"]
        assert dev.batches == [], "refused on reads alone"

    def test_the_management_interface_is_refused_ipv6(self, lab):
        dev = lab.make(manager=MANAGER_V6, cef="2001:DB8:FFFF::/48\n  nexthop FE80::1 "
                                               "GigabitEthernet1")
        rec = _run(lab, device={**DEVICE, "ip": "2001:DB8:2:E::1"})
        assert "GigabitEthernet4 carries r3's management address 2001:DB8:2:E::1" in rec["refused"]
        assert "`show ipv6 interface brief` on r3" in rec["refused"]
        assert dev.batches == []

    def test_mercurys_route_out_of_the_interface_is_refused_ipv4(self, lab):
        dev = lab.make(cef=CEF_VIA_GI4)
        rec = _run(lab)
        assert (f"r3 reaches Mercury ({MANAGER}) out of GigabitEthernet4 (`show ip cef "
                f"{MANAGER}` on r3: egress GigabitEthernet3, GigabitEthernet4)") in rec["refused"]
        assert dev.batches == []

    def test_mercurys_route_out_of_the_interface_is_refused_ipv6(self, lab):
        dev = lab.make(manager=MANAGER_V6,
                       cef="2001:DB8:FFFF::/48\n  nexthop FE80::5054:FF:FE00:4 GigabitEthernet4")
        rec = _run(lab, device={**DEVICE, "ip": "2001:DB8:2:E::9"})
        assert f"`show ipv6 cef {MANAGER_V6.lower()}` on r3" in rec["refused"]
        assert "out of GigabitEthernet4" in rec["refused"]
        assert dev.batches == []

    def test_an_egress_it_cannot_read_is_refused(self, lab):
        dev = lab.make(cef="% Invalid input detected at '^' marker.")
        rec = _run(lab)
        assert "names no egress the probe can read" in rec["refused"]
        assert dev.batches == []

    def test_a_port_already_shut_or_unknown_or_a_revert_pending_is_refused(self, lab):
        dev = lab.make()
        dev.shut.add("GigabitEthernet4")
        assert "is administratively down before the run" in _run(lab)["refused"]
        dev.shut.clear()
        assert "not an interface's state" in _run(lab, interface="GigabitEthernet9")["refused"]
        dev.pending = {"expires": T0 + 600, "n": 10, "shut": set()}
        assert "already has a revert pending" in _run(lab)["refused"]
        assert dev.batches == []


# ---------------------------------------------------------------------------- the two paths

class TestThePlannedWindow:
    """C2702 (trial 1a, r4, 2026-11-07): the probe's own bounce raised two unexplained adjacency
    flap rows, because it declared no planned window. It declares one BEFORE the batch."""

    def test_the_window_is_recorded_before_the_batch_and_covers_the_run(self, lab):
        from modules import restarts

        lab.make()
        rec = _run(lab)
        w = rec["planned_window"]
        assert w["ok"], w
        row = w["record"]
        assert (row["devices"], row["list"], row["via"]) == (["r3"], "Lab", "nmas-revert-probe")
        assert row["from"] <= rec["times"]["t0_utc"].replace(".0Z", "Z")
        assert P.window_seconds(1) == 60 + P.WATCH_PAST_S + P.WINDOW_MARGIN_S
        assert "GigabitEthernet4 shut and no shut" in row["why"]
        assert [r["devices"] for r in restarts.planned_rows()] == [["r3"]]

    @pytest.mark.parametrize("family", ["ipv4", "ipv6"])
    def test_the_window_covers_the_links_far_end(self, lab, monkeypatch, family):
        # C2749 (the operator, 2026-11-08): trial 1a's bounce of r4's port left r3's side of
        # the link unexplained; the window names the far end's device and interface.
        from modules import restarts

        only = {h: {"interfaces": [{k: v for k, v in i.items() if k in ("name", family)}
                                   for i in hv["interfaces"]]} for h, hv in LINK.items()}
        monkeypatch.setattr(P, "_intents", lambda l: (only, ""))
        lab.make()
        row = _run(lab)["planned_window"]["record"]
        assert row["expected"]["far_ends"] == [{"device": "r4",
                                                "interface": "GigabitEthernet4"}], row
        got = restarts.explained_by("r4", "Lab", restarts._epoch(row["from"]) + 5)
        assert got and got["how"] == "far_end" and "far end of r3" in got["words"], got

    def test_intent_that_cannot_be_read_sends_nothing(self, lab, monkeypatch):
        dev = lab.make()
        monkeypatch.setattr(P, "_intents", lambda l: (None, "the repository is unreadable"))
        rec = _run(lab)
        assert dev.batches == [], "nothing was sent"
        assert "far end of r3 GigabitEthernet4 cannot be told" in rec["refused"], rec

    def test_a_window_that_cannot_be_recorded_sends_nothing(self, lab, monkeypatch):
        dev = lab.make()
        monkeypatch.setattr("modules.restarts.record_planned",
                            lambda *a, **k: {"ok": False, "error": "the store is unreadable"})
        rec = _run(lab)
        assert dev.batches == [], "nothing was sent"
        assert rec["refused"].startswith("the planned window for the bounce could not be "
                                         "recorded (the store is unreadable)")

    def test_a_window_whose_record_raises_sends_nothing(self, lab, monkeypatch):
        dev = lab.make()

        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr("modules.restarts.record_planned", boom)
        rec = _run(lab)
        assert dev.batches == [] and "OSError: disk full" in rec["refused"]


class TestTheRevertPath:
    def test_the_record(self, lab):
        dev = lab.make()
        rec = _run(lab)
        assert rec["verdict"]["result"] == "PASS", rec["verdict"]
        assert dev.batches == [P.program("GigabitEthernet4", 1)], "one batch, no confirm"
        t = rec["times"]
        assert (t["t2"] - T0, t["t1"] - T0, t["settle_s"]) == (10, 10, 10.0)
        assert t["t0_utc"] == "2026-11-04T14:00:00.0Z"
        assert rec["timer_unit"]["word"] == "minutes" and rec["timer_unit"]["seconds"] == 60
        assert rec["revert"]["pending_after_timer"] is False
        assert any("ROLLBACK_START" in x for x in rec["revert"]["log_after_timer"])
        assert rec["final"]["equal"] and rec["final"]["port"]["up_up"]
        assert "repair" not in rec
        assert len(rec["attempts"]) == 6, "a session every 10 s, until the timer ended"

    def test_a_lost_session_is_measured_and_the_device_reverts(self, lab):
        """The batch's session lost at the send (the device received it whole), and no
        session for 25 s after."""
        lab.make(lose_batch_session=True, unreachable=((1, 25),))
        rec = _run(lab)
        assert rec["batch"]["lost"] == "OSError: Socket is closed"
        assert [a["ok"] for a in rec["attempts"][:3]] == [False, False, True]
        assert rec["times"]["t2"] - T0 == 30
        assert rec["verdict"]["result"] == "PASS"

    def test_a_batch_cut_after_shutdown_is_reverted_by_the_timer(self, lab):
        dev = lab.make(drop_after="shutdown")
        rec = _run(lab)
        assert "GigabitEthernet4" not in dev.shut, "the timer restored no shutdown"
        assert rec["times"]["settle_s"] >= 60, "settled only once the revert brought it up"
        assert rec["final"]["equal"] and rec["verdict"]["result"] == "PASS", rec["verdict"]

    def test_a_unit_never_stated_fails_the_run_and_is_never_assumed(self, lab):
        lab.make(unit_word=None)
        rec = _run(lab)
        assert "timer_unit" not in rec
        assert "the timer's unit stated by the device" in rec["verdict"]["failed"]


class TestTheConfirmPath:
    def test_the_record(self, lab):
        dev = lab.make()
        rec = _run(lab, path="confirm")
        assert rec["verdict"]["result"] == "PASS", rec["verdict"]
        assert dev.batches[1] == ["configure confirm"]
        assert rec["confirm"]["errors"] == [] and rec["revert"]["log_after_timer"] == []
        assert rec["times"]["settle_s"] == 10.0

    def test_no_confirm_when_the_session_returns_after_the_timer(self, lab):
        dev = lab.make(unreachable=((1, 95),))
        rec = _run(lab, path="confirm")
        assert ["configure confirm"] not in dev.batches
        assert "not confirmed" in rec["confirm"]["not_sent"]
        assert "configure confirm sent and accepted" in rec["verdict"]["failed"]
        assert rec["final"]["equal"] and "repair" not in rec

    def test_the_sheet_line_once_both_paths_passed(self, lab, tmp_path):
        lab.make(up_delay=45)
        first = _run(lab, out=str(tmp_path))
        P.write_record(first, str(tmp_path))
        assert "waits on the confirm path's PASS record" in first["sheet_line"]
        lab.clock.now = T0 + 3600
        lab.make(up_delay=45)
        second = _run(lab, path="confirm", out=str(tmp_path))
        files = P.write_record(second, str(tmp_path))
        assert second["verdict"]["result"] == "PASS", second["verdict"]
        s = first["times"]["settle_s"]
        assert s == 50.0, "the port read every second within a session"
        assert re.fullmatch(r"C2424 r3 PASS 2026-11-04T15:00:00\.0Z: .* settle 50/50 s; "
                            r"C2425 n = 3 minutes\.", second["sheet_line"]), second["sheet_line"]
        assert second["sheet_line"] in open(files[1], encoding="utf-8").read()
        assert oct(os.stat(files[0]).st_mode & 0o777) == "0o600"


# ---------------------------------------------------------------------------- errors, repairs

class TestErrorsAndRepairs:
    def test_a_device_error_stops_the_run_and_repairs(self, lab):
        """A device without an archive refuses the timer; the rest of the batch lands in exec
        mode and is refused too."""
        dev = lab.make(archive=False)
        rec = _run(lab)
        assert rec["stopped"][0].startswith("% Rollback Confirmed Change needs an archive")
        assert rec["attempts"] == [], "stopped: no watch"
        assert rec["repair"]["restored"] and rec["repair"]["steps"][-1]["step"] == "read back"
        assert len(dev.batches) == 1, "nothing to repair: nothing more was sent"

    def test_an_unknown_command_stops_and_the_repair_unshuts_and_confirms(self, lab):
        dev = lab.make(refuse_once={"no shutdown"})
        rec = _run(lab)
        assert rec["stopped"] == ["% Incomplete command."]
        steps = {s["step"]: s for s in rec["repair"]["steps"]}
        assert steps["no shutdown"]["sent"] == ["configure terminal", "interface GigabitEthernet4",
                                                "no shutdown", "end"]
        assert "is now: GigabitEthernet4 is" in steps["no shutdown"]["achieved"]
        assert steps["configure confirm"]["achieved"] == "no revert pending now"
        assert rec["repair"]["restored"] and "GigabitEthernet4" not in dev.shut

    def test_a_confirm_refused_stops_and_repairs(self, lab):
        lab.make(refuse={"configure confirm"})
        rec = _run(lab, path="confirm")
        assert rec["stopped"] == ["% Incomplete command."]
        assert "repair" in rec

    def test_a_failed_repair_says_not_restored_first(self, lab, monkeypatch, capsys, tmp_path):
        dev = lab.make(refuse={"no shutdown"})
        monkeypatch.setattr(P, "_device", lambda *a: dict(DEVICE))
        monkeypatch.setattr(P, "_intents", lambda l: ({"r3": {"archive": {"path": "b:a"}}}, ""))
        monkeypatch.setattr(P, "radius_refusal", lambda *a: "")
        monkeypatch.setattr("modules.redact.known_secret_values", lambda: {})
        monkeypatch.setattr("sys.argv", ["nmas-revert-probe", "--list", "Lab", "--device", "r3",
                                         "--interface", "GigabitEthernet4", "--timer", "1",
                                         "--apply", "--actor", "op@example.invalid", "--out",
                                         str(tmp_path)])
        assert P.main() == 2
        out = capsys.readouterr().out
        assert out.splitlines()[0].startswith("NOT RESTORED: r3:")
        assert "GigabitEthernet4" in dev.shut

    def test_a_repair_that_cannot_reach_the_device_is_not_restored(self, lab):
        dev = lab.make(archive=False)

        def lost_after_the_first():
            if dev.opened >= 1:
                dev.unreachable = ((-10 ** 9, 10 ** 9),)

        dev.on_open = lost_after_the_first
        rec = _run(lab)
        assert rec["final"]["read"] is False
        assert rec["repair"]["restored"] is False
        assert "not opened" in rec["repair"]["steps"][0]["achieved"]


# ---------------------------------------------------------------------------- never, always

SCENARIOS = [dict(), dict(path="confirm"), dict(drop_after="shutdown"),
             dict(archive=False), dict(refuse_once={"no shutdown"}),
             dict(refuse={"no shutdown"}), dict(lose_batch_session=True, unreachable=((1, 25),))]


class TestNeverSavesAndHolds:
    @pytest.mark.parametrize("kw", SCENARIOS)
    def test_no_save_is_ever_sent(self, lab, kw):
        kw = dict(kw)
        path = kw.pop("path", "revert")
        dev = lab.make(**kw)
        _run(lab, path=path)
        assert dev.sent, "the scenario sent something"
        assert dev.saves == [] and not any(SAVE.match(x) for x in dev.sent), dev.sent

    @pytest.mark.parametrize("save", ["write memory", "wr", "copy running-config startup-config",
                                      "do write", "copy system:running-config nvram:startup-config"])
    def test_a_save_is_refused_by_every_send(self, lab, save):
        dev = lab.make()
        r = P.Run(_args(), dict(DEVICE), {})
        with pytest.raises(P.SaveRefused):
            r.send(Conn(dev), ["end", save])
        assert dev.sent == []

    def test_the_device_is_held_throughout_and_a_second_operation_refused_by_name(self, lab):
        dev = lab.make()
        refusals = []

        def other():
            try:
                D.acquire("Lab", "r3", "deploy", "other@example.invalid")
                D.release("Lab", "r3")
                refusals.append("")
            except D.DeviceBusy as exc:
                refusals.append(str(exc))

        def at_open():
            t = threading.Thread(target=other)
            t.start()
            t.join(5)

        dev.on_open = at_open
        rec = _run(lab, path="confirm")
        assert rec["verdict"]["result"] == "PASS"
        assert len(refusals) >= 3 and all(refusals), refusals
        assert all("probe" in r for r in refusals), refusals[0]
        D.acquire("Lab", "r3", "deploy", "other@example.invalid")
        D.release("Lab", "r3")

    def test_the_record_is_masked(self, lab, tmp_path):
        """A log line holding a secret, new after the batch, reaches the record masked."""
        secret = "Zq9SecretValue77"
        dev = lab.make()
        line = f"*Nov  4: %ARCHIVE_DIFF-5-ROLLBK_X: archive note {secret} kept"

        def leak():
            if dev.batches and line not in dev.log:
                dev.log.append(line)

        dev.on_open = leak
        rec = P.run(_args(), dict(DEVICE), {secret: "a test secret"})
        text = json.dumps(rec)
        assert "ROLLBK_X: archive note" in text, "the line is in the record"
        assert secret not in text
